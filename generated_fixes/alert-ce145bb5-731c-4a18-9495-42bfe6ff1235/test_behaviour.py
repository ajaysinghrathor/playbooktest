import pytest
from unittest.mock import patch, MagicMock
import fix


@pytest.fixture
def mock_mysql_connection():
    with patch('fix.pymysql.connect') as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        yield mock_conn, mock_cursor


def test_given_high_thread_count_when_remediation_runs_then_idle_connections_killed(mock_mysql_connection):
    mock_conn, mock_cursor = mock_mysql_connection
    
    mock_cursor.fetchone.side_effect = [
        {'Value': '600'},
        {'Value': '1000'},
        {'Value': '550'}
    ]
    
    mock_cursor.fetchall.side_effect = [
        [
            {'id': 100, 'user': 'app', 'host': '10.1.1.1', 'db': 'testdb', 'command': 'Sleep', 'time': 350, 'state': '', 'info': None},
            {'id': 101, 'user': 'app', 'host': '10.1.1.2', 'db': 'testdb', 'command': 'Sleep', 'time': 400, 'state': '', 'info': None}
        ],
        []
    ]
    
    with patch('sys.argv', ['fix.py', '--host', 'localhost', '--user', 'admin', '--password', 'secret']):
        with patch('time.sleep'):
            result = fix.main()
    
    assert result == 0
    
    kill_calls = [call for call in mock_cursor.execute.call_args_list if 'KILL' in str(call)]
    assert len(kill_calls) >= 2


def test_given_long_running_queries_when_remediation_runs_then_queries_terminated(mock_mysql_connection):
    mock_conn, mock_cursor = mock_mysql_connection
    
    mock_cursor.fetchone.side_effect = [
        {'Value': '650'},
        {'Value': '1000'},
        {'Value': '620'}
    ]
    
    mock_cursor.fetchall.side_effect = [
        [],
        [
            {'id': 200, 'user': 'app', 'host': '10.1.1.1', 'db': 'testdb', 'command': 'Query', 'time': 800, 'state': 'Sending data', 'info': 'SELECT * FROM huge_table'},
            {'id': 201, 'user': 'app', 'host': '10.1.1.2', 'db': 'testdb', 'command': 'Query', 'time': 900, 'state': 'Locked', 'info': 'UPDATE users SET status=1'}
        ]
    ]
    
    with patch('sys.argv', ['fix.py', '--host', 'localhost', '--user', 'admin', '--password', 'secret']):
        with patch('time.sleep'):
            result = fix.main()
    
    assert result == 0
    
    kill_calls = [call for call in mock_cursor.execute.call_args_list if 'KILL' in str(call)]
    assert len(kill_calls) >= 2


def test_given_thread_count_below_threshold_when_remediation_runs_then_no_action_taken(mock_mysql_connection):
    mock_conn, mock_cursor = mock_mysql_connection
    
    mock_cursor.fetchone.return_value = {'Value': '450'}
    
    with patch('sys.argv', ['fix.py', '--host', 'localhost', '--user', 'admin', '--password', 'secret']):
        result = fix.main()
    
    assert result == 0
    
    kill_calls = [call for call in mock_cursor.execute.call_args_list if 'KILL' in str(call)]
    assert len(kill_calls) == 0


def test_given_near_max_connections_when_remediation_runs_then_max_connections_increased(mock_mysql_connection):
    mock_conn, mock_cursor = mock_mysql_connection
    
    mock_cursor.fetchone.side_effect = [
        {'Value': '980'},
        {'Value': '1000'},
        {'Value': '1000'},
        {'Value': '930'}
    ]
    
    mock_cursor.fetchall.side_effect = [
        [{'id': i, 'user': 'app', 'host': 'h', 'db': 'db', 'command': 'Sleep', 'time': 350, 'state': '', 'info': None} for i in range(100, 120)],
        []
    ]
    
    with patch('sys.argv', ['fix.py', '--host', 'localhost', '--user', 'admin', '--password', 'secret']):
        with patch('time.sleep'):
            result = fix.main()
    
    assert result == 0
    
    set_global_calls = [call for call in mock_cursor.execute.call_args_list if 'SET GLOBAL max_connections' in str(call)]
    assert len(set_global_calls) >= 1


def test_given_dry_run_mode_when_remediation_runs_then_no_actual_changes_made(mock_mysql_connection):
    mock_conn, mock_cursor = mock_mysql_connection
    
    mock_cursor.fetchone.side_effect = [
        {'Value': '600'},
        {'Value': '1000'},
        {'Value': '600'}
    ]
    
    mock_cursor.fetchall.side_effect = [
        [{'id': 100, 'user': 'app', 'host': 'h', 'db': 'db', 'command': 'Sleep', 'time': 400, 'state': '', 'info': None}],
        []
    ]
    
    with patch('sys.argv', ['fix.py', '--host', 'localhost', '--user', 'admin', '--password', 'secret', '--dry-run']):
        with patch('time.sleep'):
            result = fix.main()
    
    assert result == 0
    
    kill_calls = [call for call in mock_cursor.execute.call_args_list if 'KILL' in str(call)]
    assert len(kill_calls) == 0


def test_given_connection_failure_when_remediation_runs_then_exits_with_error(mock_mysql_connection):
    with patch('fix.pymysql.connect') as mock_connect:
        mock_connect.side_effect = Exception("Connection refused")
        
        with patch('sys.argv', ['fix.py', '--host', 'badhost', '--user', 'admin', '--password', 'secret']):
            result = fix.main()
        
        assert result == 1