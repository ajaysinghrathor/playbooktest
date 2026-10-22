#!/usr/bin/env python3
import pytest
import subprocess
import sys
import os
import time
import signal

sys.path.insert(0, os.path.dirname(__file__))
import fix


@pytest.mark.integration
def test_get_top_cpu_processes_real():
    processes = fix.get_top_cpu_processes(limit=5)
    assert isinstance(processes, list)
    if processes:
        assert 'pid' in processes[0]
        assert 'cpu' in processes[0]
        assert 'command' in processes[0]


@pytest.mark.integration
def test_renice_own_process():
    my_pid = str(os.getpid())
    result = fix.renice_process(my_pid, 10)
    assert result is True


@pytest.mark.integration
def test_kill_process_nonexistent():
    fake_pid = '999999'
    result = fix.kill_process(fake_pid, signal.SIGTERM)
    assert result is True


@pytest.mark.integration
def test_is_safe_to_kill_real_systemd():
    process = {'user': 'root', 'pid': '1', 'cpu': '0.0', 'mem': '0.1', 'command': '/sbin/init'}
    assert fix.is_safe_to_kill(process) is False


@pytest.mark.integration
def test_remediate_high_cpu_execution():
    result = fix.remediate_high_cpu()
    assert result in [0, 1]


@pytest.mark.integration
@pytest.mark.skipif(not os.path.exists('/usr/bin/cpulimit'), reason="cpulimit not installed")
def test_apply_cpulimit_real():
    proc = subprocess.Popen(['sleep', '60'])
    pid = str(proc.pid)
    try:
        result = fix.apply_cpulimit(pid, 20)
        assert result is True
        time.sleep(1)
        subprocess.run(['pkill', '-9', 'cpulimit'], check=False)
    finally:
        proc.kill()
        proc.wait()


@pytest.mark.integration
def test_main_script_execution():
    script_path = os.path.join(os.path.dirname(__file__), 'fix.py')
    result = subprocess.run(
        [sys.executable, script_path],
        capture_output=True,
        text=True,
        timeout=30
    )
    assert result.returncode in [0, 1]
    assert 'Starting CPU remediation script' in result.stdout