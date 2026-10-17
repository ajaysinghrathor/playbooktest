import pytest
from unittest.mock import Mock, patch, MagicMock, call
import sys
sys.path.insert(0, '/app/generated_fixes/alert-06f5ea39-eedf-4081-a376-bbc96e547c88')

from fix import MySQLConnectionRemediator


@pytest.fixture
def mock_connection():
    return MagicMock()


@pytest.fixture
def remediator(mock_connection):
    with patch('fix.pymysql.connect', return_value=mock_connection):
        r = MySQLConnectionRemediator(
            host='localhost',
            port=3306,
            user='test',
            password='test',
            threshold=551,
            max_idle_time=300
        )
        r.connection = mock_connection
        return r


def test_get_thread_count(remediator, mock_connection):
    cursor_mock = MagicMock()
    cursor_mock.fetchone.return_value = {'Value': '650'}
    mock_connection.cursor.return_value.__enter__.return_value = cursor_mock
    
    count = remediator.get_thread_count()
    
    assert count == 650
    cursor_mock.execute.assert_called_once_with("SHOW STATUS LIKE 'Threads_connected'")


def test_get_idle_connections(remediator, mock_connection):
    cursor_mock = MagicMock()
    cursor_mock.fetchall.return_value = [
        {'id': 1, 'user': 'app', 'host': 'host1', 'db': 'db1', 'command': 'Sleep', 'time': 400, 'state': '', 'info': None},
        {'id': 2, 'user': 'app', 'host': 'host2', 'db': 'db1', 'command': 'Sleep', 'time': 500, 'state': '', 'info': None}
    ]
    mock_connection.cursor.return_value.__enter__.return_value = cursor_mock
    
    idle = remediator.get_idle_connections()
    
    assert len(idle) == 2
    assert idle[0]['id'] == 1
    assert cursor_mock.execute.call_count == 1


def test_kill_connection_success(remediator, mock_connection):
    cursor_mock = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = cursor_mock
    
    result = remediator.kill_connection(123)
    
    assert result is True
    cursor_mock.execute.assert_called_once_with("KILL 123")


def test_kill_connection_failure(remediator, mock_connection):
    cursor_mock = MagicMock()
    cursor_mock.execute.side_effect = Exception("Connection not found")
    mock_connection.cursor.return_value.__enter__.return_value = cursor_mock
    
    result = remediator.kill_connection(999)
    
    assert result is False


def test_remediate_within_threshold(remediator, mock_connection):
    cursor_mock = MagicMock()
    cursor_mock.fetchone.return_value = {'Value': '500'}
    mock_connection.cursor.return_value.__enter__.return_value = cursor_mock
    
    final, killed = remediator.remediate()
    
    assert final == 500
    assert killed == 0


def test_remediate_exceeds_threshold(remediator, mock_connection):
    cursor_mock = MagicMock()
    cursor_mock.fetchone.side_effect = [
        {'Value': '600'},
        {'Value': '600'},
        {'Value': '550'},
        {'Value': '540'}
    ]
    cursor_mock.fetchall.return_value = [
        {'id': 10, 'user': 'app', 'host': 'h1', 'db': 'db', 'command': 'Sleep', 'time': 400, 'state': '', 'info': None},
        {'id': 11, 'user': 'app', 'host': 'h2', 'db': 'db', 'command': 'Sleep', 'time': 500, 'state': '', 'info': None}
    ]
    mock_connection.cursor.return_value.__enter__.return_value = cursor_mock
    
    final, killed = remediator.remediate()
    
    assert killed == 2
    assert final == 540


def test_connect_success():
    with patch('fix.pymysql.connect') as mock_connect:
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        
        r = MySQLConnectionRemediator('host', 3306, 'user', 'pass', 551, 300)
        r.connect()
        
        assert r.connection == mock_conn
        mock_connect.assert_called_once()


def test_connect_failure():
    with patch('fix.pymysql.connect', side_effect=Exception("Connection refused")):
        r = MySQLConnectionRemediator('host', 3306, 'user', 'pass', 551, 300)
        
        with pytest.raises(Exception):
            r.connect()


def test_close(remediator, mock_connection):
    remediator.close()
    mock_connection.close.assert_called_once()