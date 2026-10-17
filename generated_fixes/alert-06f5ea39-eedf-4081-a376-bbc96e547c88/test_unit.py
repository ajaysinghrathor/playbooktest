import pytest
from unittest.mock import Mock, MagicMock, patch, call
import sys
from io import StringIO

sys.path.insert(0, '/app/generated_fixes/alert-06f5ea39-eedf-4081-a376-bbc96e547c88')
from fix import MySQLConnectionRemediator, IDLE_TIMEOUT_SECONDS, MAX_QUERY_TIME_SECONDS, THREAD_THRESHOLD


@pytest.fixture
def remediator():
    return MySQLConnectionRemediator(host='localhost', port=3306, user='admin', password='secret')


@pytest.fixture
def mock_connection():
    return MagicMock()


def test_init(remediator):
    assert remediator.host == 'localhost'
    assert remediator.port == 3306
    assert remediator.user == 'admin'
    assert remediator.password == 'secret'


@patch('fix.pymysql.connect')
def test_connect_success(mock_connect, remediator):
    mock_conn = MagicMock()
    mock_connect.return_value = mock_conn
    remediator.connect()
    assert remediator.connection == mock_conn
    mock_connect.assert_called_once()


@patch('fix.pymysql.connect')
def test_connect_failure(mock_connect, remediator):
    mock_connect.side_effect = Exception('Connection failed')
    with pytest.raises(Exception, match='Connection failed'):
        remediator.connect()


def test_get_thread_count(remediator, mock_connection):
    remediator.connection = mock_connection
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = ('Threads_connected', '650')
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
    
    count = remediator.get_thread_count()
    assert count == 650


def test_identify_idle_connections(remediator):
    processes = [
        {'Id': 1, 'User': 'app', 'Command': 'Sleep', 'Time': 400},
        {'Id': 2, 'User': 'app', 'Command': 'Sleep', 'Time': 100},
        {'Id': 3, 'User': 'root', 'Command': 'Sleep', 'Time': 500},
        {'Id': 4, 'User': 'app', 'Command': 'Query', 'Time': 400},
    ]
    idle = remediator.identify_idle_connections(processes)
    assert idle == [1]


def test_identify_long_queries(remediator):
    processes = [
        {'Id': 1, 'User': 'app', 'Command': 'Query', 'Time': 700},
        {'Id': 2, 'User': 'app', 'Command': 'Query', 'Time': 100},
        {'Id': 3, 'User': 'root', 'Command': 'Query', 'Time': 800},
        {'Id': 4, 'User': 'app', 'Command': 'Sleep', 'Time': 700},
    ]
    long_queries = remediator.identify_long_queries(processes)
    assert long_queries == [1]


def test_kill_connection_success(remediator, mock_connection):
    remediator.connection = mock_connection
    mock_cursor = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
    
    result = remediator.kill_connection(123)
    assert result is True
    mock_cursor.execute.assert_called_once_with('KILL 123')


def test_kill_connection_failure(remediator, mock_connection):
    remediator.connection = mock_connection
    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = Exception('Kill failed')
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
    
    result = remediator.kill_connection(123)
    assert result is False


@patch('fix.time.sleep')
def test_remediate_below_threshold(mock_sleep, remediator, mock_connection):
    remediator.connection = mock_connection
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = ('Threads_connected', '500')
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
    
    initial, killed, final = remediator.remediate()
    assert initial == 500
    assert killed == 0
    assert final == 500


@patch('fix.time.sleep')
def test_remediate_kills_idle_connections(mock_sleep, remediator, mock_connection):
    remediator.connection = mock_connection
    
    mock_cursor_count = MagicMock()
    mock_cursor_count.fetchone.side_effect = [
        ('Threads_connected', '600'),
        ('Threads_connected', '600'),
        ('Threads_connected', '550'),
    ]
    
    mock_cursor_processlist = MagicMock()
    mock_cursor_processlist.fetchall.return_value = [
        {'Id': 100, 'User': 'app', 'Command': 'Sleep', 'Time': 400},
        {'Id': 101, 'User': 'app', 'Command': 'Sleep', 'Time': 350},
    ]
    
    mock_cursor_kill = MagicMock()
    
    def cursor_factory(*args, **kwargs):
        if kwargs.get('cursor') == 'DictCursor':
            return MagicMock(__enter__=MagicMock(return_value=mock_cursor_processlist))
        if not args and not kwargs:
            call_count = cursor_factory.call_count
            cursor_factory.call_count += 1
            if call_count in [0, 2, 4]:
                return MagicMock(__enter__=MagicMock(return_value=mock_cursor_count))
            return MagicMock(__enter__=MagicMock(return_value=mock_cursor_kill))
        return MagicMock(__enter__=MagicMock(return_value=mock_cursor_kill))
    
    cursor_factory.call_count = 0
    mock_connection.cursor.side_effect = cursor_factory
    
    with patch.object(remediator, 'get_thread_count', side_effect=[600, 600, 550]):
        with patch.object(remediator, 'get_processlist', return_value=[
            {'Id': 100, 'User': 'app', 'Command': 'Sleep', 'Time': 400},
        ]):
            with patch.object(remediator, 'kill_connection', return_value=True) as mock_kill:
                initial, killed, final = remediator.remediate()
                assert killed == 1
                mock_kill.assert_called()