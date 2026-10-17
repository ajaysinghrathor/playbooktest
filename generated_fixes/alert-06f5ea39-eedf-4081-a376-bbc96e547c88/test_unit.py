import pytest
from unittest.mock import MagicMock, patch, call
import sys
import pymysql

sys.path.insert(0, 'generated_fixes/alert-06f5ea39-eedf-4081-a376-bbc96e547c88')
from fix import MySQLConnectionRemediator


@pytest.fixture
def mock_connection():
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


def test_connect_success():
    with patch('fix.pymysql.connect') as mock_connect:
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        remediator = MySQLConnectionRemediator('localhost', 3306, 'user', 'pass', 300, 60, 50)
        remediator.connect()
        assert remediator.connection == mock_conn
        mock_connect.assert_called_once()


def test_connect_failure():
    with patch('fix.pymysql.connect', side_effect=Exception('Connection failed')):
        remediator = MySQLConnectionRemediator('localhost', 3306, 'user', 'pass', 300, 60, 50)
        with pytest.raises(Exception, match='Connection failed'):
            remediator.connect()


def test_get_thread_count(mock_connection):
    conn, cursor = mock_connection
    cursor.fetchone.return_value = ('Threads_connected', '600')
    remediator = MySQLConnectionRemediator('localhost', 3306, 'user', 'pass', 300, 60, 50)
    remediator.connection = conn
    count = remediator.get_thread_count()
    assert count == 600
    cursor.execute.assert_called_once()


def test_get_idle_connections(mock_connection):
    conn, cursor = mock_connection
    cursor.fetchall.return_value = [
        {'id': 100, 'user': 'app', 'host': '10.0.0.1', 'time': 400, 'command': 'Sleep'},
        {'id': 101, 'user': 'app', 'host': '10.0.0.2', 'time': 350, 'command': 'Sleep'}
    ]
    remediator = MySQLConnectionRemediator('localhost', 3306, 'user', 'pass', 300, 60, 50)
    remediator.connection = conn
    idle = remediator.get_idle_connections()
    assert len(idle) == 2
    assert idle[0]['id'] == 100


def test_get_long_running_queries(mock_connection):
    conn, cursor = mock_connection
    cursor.fetchall.return_value = [
        {'id': 200, 'user': 'app', 'host': '10.0.0.3', 'time': 120, 'command': 'Query'}
    ]
    remediator = MySQLConnectionRemediator('localhost', 3306, 'user', 'pass', 300, 60, 50)
    remediator.connection = conn
    queries = remediator.get_long_running_queries()
    assert len(queries) == 1
    assert queries[0]['time'] == 120


def test_kill_connection_success(mock_connection):
    conn, cursor = mock_connection
    remediator = MySQLConnectionRemediator('localhost', 3306, 'user', 'pass', 300, 60, 50)
    remediator.connection = conn
    result = remediator.kill_connection(123)
    assert result is True
    cursor.execute.assert_called_with('KILL 123')


def test_kill_connection_failure(mock_connection):
    conn, cursor = mock_connection
    cursor.execute.side_effect = Exception('Kill failed')
    remediator = MySQLConnectionRemediator('localhost', 3306, 'user', 'pass', 300, 60, 50)
    remediator.connection = conn
    result = remediator.kill_connection(123)
    assert result is False


def test_remediate_kills_idle_and_long_queries():
    remediator = MySQLConnectionRemediator('localhost', 3306, 'user', 'pass', 300, 60, 5)
    remediator.connection = MagicMock()
    
    with patch.object(remediator, 'get_thread_count', side_effect=[600, 550]):
        with patch.object(remediator, 'get_idle_connections', return_value=[
            {'id': 1, 'user': 'app', 'host': '10.0.0.1', 'time': 400}
        ]):
            with patch.object(remediator, 'get_long_running_queries', return_value=[
                {'id': 2, 'user': 'app', 'host': '10.0.0.2', 'time': 120}
            ]):
                with patch.object(remediator, 'kill_connection', return_value=True) as mock_kill:
                    killed = remediator.remediate()
                    assert killed == 2
                    assert mock_kill.call_count == 2


def test_remediate_no_connections_to_kill():
    remediator = MySQLConnectionRemediator('localhost', 3306, 'user', 'pass', 300, 60, 50)
    remediator.connection = MagicMock()
    
    with patch.object(remediator, 'get_thread_count', return_value=400):
        with patch.object(remediator, 'get_idle_connections', return_value=[]):
            with patch.object(remediator, 'get_long_running_queries', return_value=[]):
                killed = remediator.remediate()
                assert killed == 0