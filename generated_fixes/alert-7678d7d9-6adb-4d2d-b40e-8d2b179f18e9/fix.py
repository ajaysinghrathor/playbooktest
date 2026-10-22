#!/usr/bin/env python3
import os
import sys
import logging
import subprocess
import signal
from typing import List, Tuple, Dict

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

CPU_THRESHOLD_KILL = 90.0
CPU_THRESHOLD_THROTTLE = 70.0
MAX_PROCESSES_TO_HANDLE = 5
EXCLUDED_PROCESSES = {'systemd', 'sshd', 'init', 'kernel', 'bash', 'sh'}


def get_top_cpu_processes(limit: int = 10) -> List[Dict[str, str]]:
    try:
        result = subprocess.run(
            ['ps', 'aux', '--sort=-%cpu'],
            capture_output=True,
            text=True,
            check=True,
            timeout=10
        )
        lines = result.stdout.strip().split('\n')[1:]
        processes = []
        for line in lines[:limit]:
            parts = line.split(None, 10)
            if len(parts) >= 11:
                processes.append({
                    'user': parts[0],
                    'pid': parts[1],
                    'cpu': parts[2],
                    'mem': parts[3],
                    'command': parts[10]
                })
        return processes
    except subprocess.TimeoutExpired:
        logger.error("Timeout while fetching process list")
        return []
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to get process list: {e}")
        return []


def is_safe_to_kill(process: Dict[str, str]) -> bool:
    command = process['command'].lower()
    for excluded in EXCLUDED_PROCESSES:
        if excluded in command:
            return False
    if process['user'] == 'root' and any(s in command for s in ['systemd', 'journal', 'udev']):
        return False
    return True


def renice_process(pid: str, niceness: int = 19) -> bool:
    try:
        subprocess.run(['renice', '-n', str(niceness), '-p', pid], check=True, timeout=5)
        logger.info(f"Reniced process {pid} to niceness {niceness}")
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        logger.warning(f"Failed to renice process {pid}: {e}")
        return False


def apply_cpulimit(pid: str, limit_percent: int = 50) -> bool:
    if not os.path.exists('/usr/bin/cpulimit'):
        logger.warning("cpulimit not installed, skipping")
        return False
    try:
        subprocess.Popen(
            ['cpulimit', '-p', pid, '-l', str(limit_percent), '-b'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        logger.info(f"Applied cpulimit {limit_percent}% to process {pid}")
        return True
    except Exception as e:
        logger.warning(f"Failed to apply cpulimit to process {pid}: {e}")
        return False


def kill_process(pid: str, signal_type: int = signal.SIGTERM) -> bool:
    try:
        os.kill(int(pid), signal_type)
        logger.warning(f"Sent signal {signal_type} to process {pid}")
        return True
    except ProcessLookupError:
        logger.info(f"Process {pid} no longer exists")
        return True
    except PermissionError:
        logger.error(f"Permission denied to kill process {pid}")
        return False
    except Exception as e:
        logger.error(f"Failed to kill process {pid}: {e}")
        return False


def remediate_high_cpu() -> int:
    logger.info("Starting CPU remediation script")
    
    processes = get_top_cpu_processes(limit=15)
    if not processes:
        logger.error("Failed to retrieve process list")
        return 1
    
    logger.info(f"Top CPU processes: {len(processes)} found")
    
    actions_taken = 0
    for proc in processes[:MAX_PROCESSES_TO_HANDLE]:
        try:
            cpu_usage = float(proc['cpu'])
        except ValueError:
            continue
        
        pid = proc['pid']
        command = proc['command']
        
        logger.info(f"Process {pid} ({command[:50]}) using {cpu_usage}% CPU")
        
        if cpu_usage >= CPU_THRESHOLD_KILL:
            if is_safe_to_kill(proc):
                logger.warning(f"Process {pid} exceeds kill threshold ({cpu_usage}% >= {CPU_THRESHOLD_KILL}%)")
                if kill_process(pid, signal.SIGTERM):
                    actions_taken += 1
            else:
                logger.warning(f"Process {pid} exceeds threshold but is excluded from termination")
                renice_process(pid, 19)
                actions_taken += 1
        
        elif cpu_usage >= CPU_THRESHOLD_THROTTLE:
            logger.info(f"Process {pid} exceeds throttle threshold ({cpu_usage}% >= {CPU_THRESHOLD_THROTTLE}%)")
            if renice_process(pid, 15):
                actions_taken += 1
            apply_cpulimit(pid, 50)
    
    if actions_taken == 0:
        logger.info("No processes exceeded thresholds, no action needed")
    else:
        logger.info(f"Remediation complete: {actions_taken} actions taken")
    
    return 0


if __name__ == '__main__':
    try:
        sys.exit(remediate_high_cpu())
    except Exception as e:
        logger.error(f"Unhandled exception: {e}", exc_info=True)
        sys.exit(1)