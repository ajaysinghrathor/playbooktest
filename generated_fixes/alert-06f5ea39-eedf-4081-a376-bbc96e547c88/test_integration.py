import pytest
import os
import sys
from unittest.mock import patch, MagicMock
sys.path.insert(0, '/app/generated_fixes/alert-06f5ea39-eedf-4081-a376-bbc96e547c88')

from fix import MySQLConnectionRemediator, main


@pytest.mark.integration
def test_full_remediation_flow():
    mock_connection = MagicMock()
    cursor_mock = MagicMock()
    
    cursor_mock.fetchone.side_effect = [
        {'Value': '600'},
        {'Value': '600'},
        {'Value': '530'}
    ]
    cursor_mock.fetchall.return_value = [
        {'id': 100, 'user': 'app', 'host': '10.0.0.1', 'db': 'testdb', 'command': 'Sleep', 'time': 400, 'state': '', 'info': None},
        {'id': 101, 'user': 'app', 'host': '10.0.0.2', 'db': 'testdb', 'command': 'Sleep', 'time': 350, 'state': '', 'info': None}
    ]
    
    mock_connection.cursor.return_value.__enter__.return_value = cursor_mock
    
    with patch('fix.pymysql.connect', return_value=mock_connection):
        remediator = MySQLConnectionRemediator(
            host='testhost',
            port=3306,
            user='testuser',
            password='testpass',
            threshold=551,
            max_idle_time=300
        )
        remediator.connect()
        final_count, killed = remediator.remediate()
        remediator.close()
    
    assert final_count == 530
    assert killed == 2
    mock_connection.close.assert_called_once()


@pytest.mark.integration
def test_main_success_path():
    mock_connection = MagicMock()
    cursor_mock = MagicMock()
    
    cursor_mock.fetchone.side_effect = [
        {'Value': '500'}
    ]
    
    mock_connection.cursor.return_value.__enter__.return_value = cursor_mock
    
    test_args = [
        'fix.py',
        '--host', '10.244.5.1',
        '--port', '3306',
        '--user', 'admin',
        '--password', 'secret',
        '--threshold', '551',
        '--max-idle-time', '300'
    ]
    
    with patch('fix.pymysql.connect', return_value=mock_connection):
        with patch('sys.argv', test_args):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0


@pytest.mark.integration
def test_main_failure_threshold_exceeded():
    mock_connection = MagicMock()
    cursor_mock = MagicMock()
    
    cursor_mock.fetchone.side_effect = [
        {'Value': '700'},
        {'Value': '700'},
        {'Value': '680'}
    ]
    cursor_mock.fetchall.return_value = []
    
    mock_connection.cursor.return_value.__enter__.return_value = cursor_mock
    
    test_args = [
        'fix.py',
        '--host', 'localhost',
        '--user', 'root',
        '--password', 'pass',
        '--threshold', '551'
    ]
    
    with patch('fix.pymysql.connect', return_value=mock_connection):
        with patch('sys.argv', test_args):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1


@pytest.mark.integration
def test_main_connection_failure():
    test_args = [
        'fix.py',
        '--host', 'invalid_host',
        '--user', 'user',
        '--password', 'pass'
    ]
    
    with patch('fix.pymysql.connect', side_effect=Exception("Connection error")):
        with patch('sys.argv', test_args):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1