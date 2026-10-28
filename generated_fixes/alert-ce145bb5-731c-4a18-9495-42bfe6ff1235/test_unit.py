import pytest
from unittest.mock import Mock, MagicMock, patch, call
import sys

with patch.dict('sys.modules', {'pymysql': MagicMock(), 'pymysql.cursors': MagicMock()}):
    import fix


def test_parse_args_with_required():
    with patch('sys.argv', ['fix.py', '--host', 'testhost', '--port', '3306', '--user', 'admin', '--password', 'secret']):
        args = fix.parse_args()
        assert args.host == 'testhost'
        assert args.port == 3306
        assert args.user == 'admin'
        assert args.password == 'secret'
        assert args.dry_run is False


def test_parse_args_with_dry_run():
    with patch('sys.argv', ['fix.py', '--host', 'h', '--user', 'u', '--password', 'p', '--dry-run']):
        args = fix.parse_args()
        assert args.dry_run is True


@patch('fix.pymysql.connect')
def test_get_connection_success(mock_connect):
    mock_conn = MagicMock()
    mock_connect.return_value = mock_conn
    
    conn = fix.get_connection('localhost', 3306, 'user', 'pass')
    
    assert conn == mock_conn
    mock_connect.assert_called_once()


@patch('fix.pymysql.connect')
def test_get_connection_failure(mock_connect):
    mock_connect.side_effect = Exception("Connection failed")
    
    with pytest.raises(Exception):
        fix.get_connection('localhost', 3306, 'user', 'pass')


def test_get_current_threads():
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchone.return_value = {'Value': '650'}
    
    count = fix.get_current_threads(mock_conn)
    
    assert count == 650
    mock_cursor.execute.assert_called_once()


def test_get_idle_connections():
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchall.return_value = [
        {'id': 100, 'user': 'app', 'host': '10.1.1.1', 'time': 400},
        {'id': 101, 'user': 'app', 'host': '10.1.1.2', 'time': 350}
    ]
    
    results = fix.get_idle_connections(mock_conn, 300)
    
    assert len(results) == 2
    assert results[0]['id'] == 100
    mock_cursor.execute.assert_called_once()


def test_get_long_running_queries():
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchall.return_value = [
        {'id': 200, 'user': 'app', 'time': 700, 'info': 'SELECT * FROM large_table'}
    ]
    
    results = fix.get_long_running_queries(mock_conn, 600)
    
    assert len(results) == 1
    assert results[0]['id'] == 200


def test_kill_connections_success():
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    
    success, failure = fix.kill_connections(mock_conn, [100, 101, 102], False)
    
    assert success == 3
    assert failure == 0
    assert mock_cursor.execute.call_count == 3


def test_kill_connections_dry_run():
    mock_conn = MagicMock()
    
    success, failure = fix.kill_connections(mock_conn, [100, 101], True)
    
    assert success == 2
    assert failure == 0
    mock_conn.cursor.assert_not_called()


def test_kill_connections_partial_failure():
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.execute.side_effect = [None, Exception("Kill failed"), None]
    
    success, failure = fix.kill_connections(mock_conn, [100, 101, 102], False)
    
    assert success == 2
    assert failure == 1


def test_get_max_connections():
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchone.return_value = {'Value': '1000'}
    
    max_conn = fix.get_max_connections(mock_conn)
    
    assert max_conn == 1000


def test_adjust_max_connections_needed():
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchone.return_value = {'Value': '1000'}
    
    result = fix.adjust_max_connections(mock_conn, 980, False)
    
    assert result is True
    assert mock_cursor.execute.call_count == 2


def test_adjust_max_connections_not_needed():
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchone.return_value = {'Value': '1000'}
    
    result = fix.adjust_max_connections(mock_conn, 500, False)
    
    assert result is False


@patch('fix.get_connection')
@patch('fix.get_current_threads')
@patch('fix.get_idle_connections')
@patch('fix.get_long_running_queries')
@patch('fix.kill_connections')
@patch('fix.adjust_max_connections')
def test_main_below_threshold(mock_adjust, mock_kill, mock_long, mock_idle, mock_threads, mock_conn):
    mock_connection = MagicMock()
    mock_conn.return_value = mock_connection
    mock_threads.return_value = 400
    
    with patch('sys.argv', ['fix.py', '--host', 'h', '--user', 'u', '--password', 'p']):
        result = fix.main()
    
    assert result == 0
    mock_idle.assert_not_called()
    mock_kill.assert_not_called()


@patch('fix.get_connection')
@patch('fix.get_current_threads')
@patch('fix.get_idle_connections')
@patch('fix.get_long_running_queries')
@patch('fix.kill_connections')
@patch('fix.adjust_max_connections')
@patch('time.sleep')
def test_main_above_threshold(mock_sleep, mock_adjust, mock_kill, mock_long, mock_idle, mock_threads, mock_conn):
    mock_connection = MagicMock()
    mock_conn.return_value = mock_connection
    mock_threads.side_effect = [600, 550]
    mock_idle.return_value = [{'id': 100, 'user': 'app', 'host': 'h', 'time': 400}]
    mock_long.return_value = [{'id': 101, 'user': 'app', 'time': 700, 'info': 'SELECT'}]
    mock_kill.return_value = (2, 0)
    mock_adjust.return_value = True
    
    with patch('sys.argv', ['fix.py', '--host', 'h', '--user', 'u', '--password', 'p']):
        result = fix.main()
    
    assert result == 0
    mock_kill.assert_called_once()
    mock_adjust.assert_called_once()