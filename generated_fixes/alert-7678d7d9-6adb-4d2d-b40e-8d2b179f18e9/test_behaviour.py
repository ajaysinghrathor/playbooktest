#!/usr/bin/env python3
import pytest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
import fix


@pytest.fixture
def mock_high_cpu_process():
    return [
        {'user': 'appuser', 'pid': '1001', 'cpu': '95.5', 'mem': '3.0', 'command': 'cpu_hog_process'}
    ]


@pytest.fixture
def mock_moderate_cpu_process():
    return [
        {'user': 'appuser', 'pid': '1002', 'cpu': '75.0', 'mem': '2.0', 'command': 'moderate_process'}
    ]


@pytest.fixture
def mock_low_cpu_processes():
    return [
        {'user': 'appuser', 'pid': '1003', 'cpu': '10.0', 'mem': '1.0', 'command': 'low_process'}
    ]


def test_given_high_cpu_process_when_remediate_then_process_is_killed(mock_high_cpu_process):
    with patch('fix.get_top_cpu_processes', return_value=mock_high_cpu_process), \
         patch('fix.kill_process', return_value=True) as mock_kill, \
         patch('fix.is_safe_to_kill', return_value=True):
        
        result = fix.remediate_high_cpu()
        
        assert result == 0
        mock_kill.assert_called_once()


def test_given_moderate_cpu_process_when_remediate_then_process_is_reniced(mock_moderate_cpu_process):
    with patch('fix.get_top_cpu_processes', return_value=mock_moderate_cpu_process), \
         patch('fix.renice_process', return_value=True) as mock_renice, \
         patch('fix.apply_cpulimit', return_value=True):
        
        result = fix.remediate_high_cpu()
        
        assert result == 0
        mock_renice.assert_called_once_with('1002', 15)


def test_given_low_cpu_processes_when_remediate_then_no_action_taken(mock_low_cpu_processes):
    with patch('fix.get_top_cpu_processes', return_value=mock_low_cpu_processes), \
         patch('fix.renice_process') as mock_renice, \
         patch('fix.kill_process') as mock_kill:
        
        result = fix.remediate_high_cpu()
        
        assert result == 0
        mock_renice.assert_not_called()
        mock_kill.assert_not_called()


def test_given_critical_system_process_when_high_cpu_then_not_killed():
    critical_process = [
        {'user': 'root', 'pid': '1', 'cpu': '95.0', 'mem': '1.0', 'command': 'systemd'}
    ]
    
    with patch('fix.get_top_cpu_processes', return_value=critical_process), \
         patch('fix.is_safe_to_kill', return_value=False), \
         patch('fix.kill_process') as mock_kill, \
         patch('fix.renice_process', return_value=True) as mock_renice:
        
        result = fix.remediate_high_cpu()
        
        assert result == 0
        mock_kill.assert_not_called()
        mock_renice.assert_called_once_with('1', 19)


def test_given_no_processes_found_when_remediate_then_returns_error():
    with patch('fix.get_top_cpu_processes', return_value=[]):
        
        result = fix.remediate_high_cpu()
        
        assert result == 1


def test_given_multiple_high_cpu_processes_when_remediate_then_handles_up_to_max():
    many_processes = [
        {'user': f'user{i}', 'pid': str(2000+i), 'cpu': '92.0', 'mem': '2.0', 'command': f'process_{i}'}
        for i in range(10)
    ]
    
    with patch('fix.get_top_cpu_processes', return_value=many_processes), \
         patch('fix.is_safe_to_kill', return_value=True), \
         patch('fix.kill_process', return_value=True) as mock_kill:
        
        result = fix.remediate_high_cpu()
        
        assert result == 0
        assert mock_kill.call_count == fix.MAX_PROCESSES_TO_HANDLE


def test_given_cpulimit_available_when_throttling_then_cpulimit_applied(mock_moderate_cpu_process):
    with patch('fix.get_top_cpu_processes', return_value=mock_moderate_cpu_process), \
         patch('fix.renice_process', return_value=True), \
         patch('fix.apply_cpulimit', return_value=True) as mock_cpulimit:
        
        result = fix.remediate_high_cpu()
        
        assert result == 0
        mock_cpulimit.assert_called_once_with('1002', 50)