import pytest
from unittest.mock import patch, Mock
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from fix import MySQLConnectionRemediator


def test_given_high_thread_count_when_remediate_then_kills_idle_connections():
    remediator = MySQLConnectionRemediator(
        host='localhost',
        port=3306,
        user='admin',
        password='pass',
        idle_threshold=300,
        max_connections=1000,
        thread_threshold=551,
        dry_run=False
    )
    
    idle_conns = [
        {'id': 101, 'user': 'app', 'host': '10.0.0.1', 'time': 400},
        {'id': 102, 'user': 'app', 'host': '10.0.0.2', 'time': 350}
    ]
    
    with patch.object(remediator, 'connect'):
        with patch.object(remediator, 'get_thread_count', side_effect=[600, 520]):
            with patch.object(remediator, 'get_idle_connections', return_value=idle_conns):
                with patch.object(remediator, 'get_max_connections', return_value=900):
                    with patch.object(remediator, 'kill_connection', return_value=True) as mock_kill:
                        with patch.object(remediator, 'set_max_connections', return_value=True):
                            with patch.object(remediator, 'flush_threads', return_value=True):
                                remediator.conn = Mock()
                                success, result = remediator.remediate()
                                
                                assert success is True
                                assert result['killed_connections'] == 2
                                assert mock_kill.call_count == 2
                                assert result['final_threads'] == 520


def test_given_thread_count_below_threshold_when_remediate_then_no_action():
    remediator = MySQLConnectionRemediator(
        host='localhost',
        port=3306,
        user='admin',
        password='pass',
        idle_threshold=300,
        max_connections=1000,
        thread_threshold=551,
        dry_run=False
    )
    
    with patch.object(remediator, 'connect'):
        with patch.object(remediator, 'get_thread_count', return_value=450):
            remediator.conn = Mock()
            success, result = remediator.remediate()
            
            assert success is True
            assert result['killed_connections'] == 0
            assert result['initial_threads'] == 450
            assert result['final_threads'] == 450


def test_given_dry_run_mode_when_remediate_then_no_actual_changes():
    remediator = MySQLConnectionRemediator(
        host='localhost',
        port=3306,
        user='admin',
        password='pass',
        idle_threshold=300,
        max_connections=1000,
        thread_threshold=551,
        dry_run=True
    )
    
    idle_conns = [{'id': 101, 'user': 'app', 'time': 400}]
    
    with patch.object(remediator, 'connect'):
        with patch.object(remediator, 'get_thread_count', side_effect=[600, 600]):
            with patch.object(remediator, 'get_idle_connections', return_value=idle_conns):
                with patch.object(remediator, 'get_max_connections', return_value=800):
                    with patch.object(remediator, 'kill_connection') as mock_kill:
                        with patch.object(remediator, 'set_max_connections') as mock_set:
                            remediator.conn = Mock()
                            success, result = remediator.remediate()
                            
                            assert success is True
                            assert result['killed_connections'] == 1
                            mock_kill.assert_not_called()
                            mock_set.assert_not_called()


def test_given_low_max_connections_when_remediate_then_increases_limit():
    remediator = MySQLConnectionRemediator(
        host='localhost',
        port=3306,
        user='admin',
        password='pass',
        idle_threshold=300,
        max_connections=1000,
        thread_threshold=551,
        dry_run=False
    )
    
    with patch.object(remediator, 'connect'):
        with patch.object(remediator, 'get_thread_count', side_effect=[600, 580]):
            with patch.object(remediator, 'get_idle_connections', return_value=[]):
                with patch.object(remediator, 'get_max_connections', return_value=600):
                    with patch.object(remediator, 'set_max_connections', return_value=True) as mock_set:
                        with patch.object(remediator, 'flush_threads', return_value=True):
                            remediator.conn = Mock()
                            success, result = remediator.remediate()
                            
                            assert success is True
                            assert result['max_connections_updated'] is True
                            mock_set.assert_called_once_with(1000)


def test_given_connection_failure_when_remediate_then_returns_failure():
    remediator = MySQLConnectionRemediator(
        host='localhost',
        port=3306,
        user='admin',
        password='pass',
        idle_threshold=300,
        max_connections=1000,
        thread_threshold=551,
        dry_run=False
    )
    
    with patch.object(remediator, 'connect', side_effect=Exception('Connection failed')):
        success, result = remediator.remediate()
        assert success is False