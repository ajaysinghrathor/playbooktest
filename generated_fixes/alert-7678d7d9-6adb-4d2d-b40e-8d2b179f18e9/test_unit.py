#!/usr/bin/env python3
import pytest
from unittest.mock import patch, MagicMock, call
import subprocess
import signal
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
import fix


@patch('fix.subprocess.run')
def test_get_top_cpu_processes_success(mock_run):
    mock_run.return_value = MagicMock(
        stdout="USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND\nuser1      123 95.5  2.3 100000 50000 ?        R    10:00   1:00 stress-ng\nuser2      456 85.0  1.5  80000 40000 ?        R    10:01   0:50 python3\n",
        returncode=0
    )
    processes = fix.get_top_cpu_processes(limit=10)
    assert len(processes) == 2
    assert processes[0]['pid'] == '123'
    assert processes[0]['cpu'] == '95.5'
    assert processes[0]['command'] == 'stress-ng'


@patch('fix.subprocess.run')
def test_get_top_cpu_processes_timeout(mock_run):
    mock_run.side_effect = subprocess.TimeoutExpired('ps', 10)
    processes = fix.get_top_cpu_processes()
    assert processes == []


def test_is_safe_to_kill_excluded():
    process = {'user': 'root', 'pid': '1', 'cpu': '10.0', 'mem': '1.0', 'command': 'systemd'}
    assert fix.is_safe_to_kill(process) is False


def test_is_safe_to_kill_safe():
    process = {'user': 'appuser', 'pid': '999', 'cpu': '95.0', 'mem': '2.0', 'command': 'stress-ng'}
    assert fix.is_safe_to_kill(process) is True


@patch('fix.subprocess.run')
def test_renice_process_success(mock_run):
    mock_run.return_value = MagicMock(returncode=0)
    result = fix.renice_process('123', 19)
    assert result is True
    mock_run.assert_called_once_with(['renice', '-n', '19', '-p', '123'], check=True, timeout=5)


@patch('fix.subprocess.run')
def test_renice_process_failure(mock_run):
    mock_run.side_effect = subprocess.CalledProcessError(1, 'renice')
    result = fix.renice_process('123', 19)
    assert result is False


@patch('fix.os.path.exists')
@patch('fix.subprocess.Popen')
def test_apply_cpulimit_success(mock_popen, mock_exists):
    mock_exists.return_value = True
    mock_popen.return_value = MagicMock()
    result = fix.apply_cpulimit('123', 50)
    assert result is True
    mock_popen.assert_called_once()


@patch('fix.os.path.exists')
def test_apply_cpulimit_not_installed(mock_exists):
    mock_exists.return_value = False
    result = fix.apply_cpulimit('123', 50)
    assert result is False


@patch('fix.os.kill')
def test_kill_process_success(mock_kill):
    result = fix.kill_process('123', signal.SIGTERM)
    assert result is True
    mock_kill.assert_called_once_with(123, signal.SIGTERM)


@patch('fix.os.kill')
def test_kill_process_not_found(mock_kill):
    mock_kill.side_effect = ProcessLookupError()
    result = fix.kill_process('123', signal.SIGTERM)
    assert result is True


@patch('fix.get_top_cpu_processes')
@patch('fix.renice_process')
@patch('fix.kill_process')
def test_remediate_high_cpu_kill_threshold(mock_kill, mock_renice, mock_get_processes):
    mock_get_processes.return_value = [
        {'user': 'testuser', 'pid': '999', 'cpu': '95.0', 'mem': '2.0', 'command': 'stress-ng'}
    ]
    mock_kill.return_value = True
    result = fix.remediate_high_cpu()
    assert result == 0
    mock_kill.assert_called_once_with('999', signal.SIGTERM)


@patch('fix.get_top_cpu_processes')
@patch('fix.renice_process')
def test_remediate_high_cpu_throttle_threshold(mock_renice, mock_get_processes):
    mock_get_processes.return_value = [
        {'user': 'testuser', 'pid': '888', 'cpu': '75.0', 'mem': '1.5', 'command': 'compute_job'}
    ]
    mock_renice.return_value = True
    result = fix.remediate_high_cpu()
    assert result == 0
    mock_renice.assert_called()


@patch('fix.get_top_cpu_processes')
def test_remediate_high_cpu_no_action_needed(mock_get_processes):
    mock_get_processes.return_value = [
        {'user': 'testuser', 'pid': '777', 'cpu': '5.0', 'mem': '1.0', 'command': 'idle_process'}
    ]
    result = fix.remediate_high_cpu()
    assert result == 0


@patch('fix.get_top_cpu_processes')
def test_remediate_high_cpu_process_list_failure(mock_get_processes):
    mock_get_processes.return_value = []
    result = fix.remediate_high_cpu()
    assert result == 1