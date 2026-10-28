import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from fix import MySQLConnectionRemediator


@pytest.fixture
def remediator():
    return MySQLConnectionRemediator(
        host='localhost',
        port=3306,
        user='testuser',
        password='testpass',
        idle_threshold=300,
        max_connections=1000,
        thread_threshold=551,
        dry_run=False
    )


def test_connect_success(remediator):
    with patch('pymysql.connect') as mock_connect:
        mock_conn = Mock()
        mock_connect.return_value = mock_conn
        remediator.connect()
        assert remediator.conn == mock_conn
        mock_connect.assert_called_once_with(
            host='localhost',
            port=3306,
            user='testuser',
            password='testpass',
            connect_timeout=10
        )


def test_connect_failure(remediator):
    with patch('pymysql.connect', side_effect=Exception('Connection failed')):
        with pytest.raises(Exception, match='Connection failed'):
            remediator.connect()


def test_get_thread_count(remediator):
    mock_conn = Mock()
    mock_cursor = Mock()
    mock_cursor.fetchone.return_value = ('Threads_connected', '600')
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    remediator.conn = mock_conn
    
    count = remediator.get_thread_count()
    assert count == 600
    mock_cursor.execute.assert_called_once_with("SHOW STATUS LIKE 'Threads_connected'")


def test_get_max_connections(remediator):
    mock_conn = Mock()
    mock_cursor = Mock()
    mock_cursor.fetchone.return_value = ('max_connections', '500')
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    remediator.conn = mock_conn
    
    max_conn = remediator.get_max_connections()
    assert max_conn == 500


def test_get_idle_connections(remediator):
    mock_conn = Mock()
    mock_cursor = Mock()
    mock_cursor.fetchall.return_value = [
        {'id': 101, 'user': 'app', 'host': '10.0.0.1', 'time': 400},
        {'id': 102, 'user': 'app', 'host': '10.0.0.2', 'time': 350}
    ]
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    remediator.conn = mock_conn
    
    idle = remediator.get_idle_connections()
    assert len(idle) == 2
    assert idle[0]['id'] == 101


def test_kill_connection_success(remediator):
    mock_conn = Mock()
    mock_cursor = Mock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    remediator.conn = mock_conn
    
    result = remediator.kill_connection(101)
    assert result is True
    mock_cursor.execute.assert_called_once_with('KILL 101')


def test_kill_connection_failure(remediator):
    mock_conn = Mock()
    mock_cursor = Mock()
    mock_cursor.execute.side_effect = Exception('Kill failed')
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    remediator.conn = mock_conn
    
    result = remediator.kill_connection(101)
    assert result is False


def test_set_max_connections_success(remediator):
    mock_conn = Mock()
    mock_cursor = Mock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    remediator.conn = mock_conn
    
    result = remediator.set_max_connections(1000)
    assert result is True
    mock_cursor.execute.assert_called_once_with('SET GLOBAL max_connections = 1000')


def test_remediate_below_threshold(remediator):
    with patch.object(remediator, 'connect'):
        with patch.object(remediator, 'get_thread_count', return_value=400):
            remediator.conn = Mock()
            success, result = remediator.remediate()
            assert success is True
            assert result['initial_threads'] == 400


def test_remediate_dry_run(remediator):
    remediator.dry_run = True
    idle_conns = [{'id': 101, 'user': 'app', 'time': 400}]
    
    with patch.object(remediator, 'connect'):
        with patch.object(remediator, 'get_thread_count', side_effect=[600, 580]):
            with patch.object(remediator, 'get_idle_connections', return_value=idle_conns):
                with patch.object(remediator, 'get_max_connections', return_value=800):
                    remediator.conn = Mock()
                    success, result = remediator.remediate()
                    assert success is True
                    assert result['killed_connections'] == 1
                    assert result['max_connections_updated'] is True


def test_remediate_full_execution(remediator):
    idle_conns = [{'id': 101, 'user': 'app', 'time': 400}]
    
    with patch.object(remediator, 'connect'):
        with patch.object(remediator, 'get_thread_count', side_effect=[600, 500]):
            with patch.object(remediator, 'get_idle_connections', return_value=idle_conns):
                with patch.object(remediator, 'get_max_connections', return_value=800):
                    with patch.object(remediator, 'kill_connection', return_value=True):
                        with patch.object(remediator, 'set_max_connections', return_value=True):
                            with patch.object(remediator, 'flush_threads', return_value=True):
                                remediator.conn = Mock()
                                success, result = remediator.remediate()
                                assert success is True
                                assert result['killed_connections'] == 1
                                assert result['final_threads'] == 500