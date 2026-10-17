import pytest
from unittest.mock import Mock, MagicMock, patch, call
import sys
sys.path.insert(0, '.')
from fix import MySQLConnectionRemediator


class TestMySQLConnectionRemediator:
    
    def test_init(self):
        rem = MySQLConnectionRemediator('localhost', 3306, 'user', 'pass', 300, 100)
        assert rem.host == 'localhost'
        assert rem.port == 3306
        assert rem.user == 'user'
        assert rem.password == 'pass'
        assert rem.idle_threshold == 300
        assert rem.max_kill == 100

    @patch('fix.pymysql.connect')
    def test_connect_success(self, mock_connect):
        mock_conn = Mock()
        mock_connect.return_value = mock_conn
        
        rem = MySQLConnectionRemediator('localhost', 3306, 'user', 'pass')
        rem.connect()
        
        assert rem.connection == mock_conn
        mock_connect.assert_called_once_with(
            host='localhost',
            port=3306,
            user='user',
            password='pass',
            connect_timeout=10,
            read_timeout=30
        )

    @patch('fix.pymysql.connect')
    def test_connect_failure(self, mock_connect):
        mock_connect.side_effect = Exception('Connection failed')
        
        rem = MySQLConnectionRemediator('localhost', 3306, 'user', 'pass')
        with pytest.raises(Exception, match='Connection failed'):
            rem.connect()

    def test_get_thread_count(self):
        rem = MySQLConnectionRemediator('localhost', 3306, 'user', 'pass')
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = ('Threads_connected', '555')
        rem.connection = Mock()
        rem.connection.cursor.return_value = mock_cursor
        
        count = rem.get_thread_count()
        
        assert count == 555
        mock_cursor.execute.assert_called_once_with("SHOW STATUS LIKE 'Threads_connected'")
        mock_cursor.close.assert_called_once()

    def test_get_idle_connections(self):
        rem = MySQLConnectionRemediator('localhost', 3306, 'user', 'pass', 300, 100)
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [
            {'ID': 101, 'USER': 'app', 'TIME': 350},
            {'ID': 102, 'USER': 'app', 'TIME': 400}
        ]
        rem.connection = Mock()
        rem.connection.cursor.return_value = mock_cursor
        
        idle = rem.get_idle_connections()
        
        assert len(idle) == 2
        assert idle[0]['ID'] == 101
        mock_cursor.execute.assert_called_once()
        mock_cursor.close.assert_called_once()

    def test_kill_connection_success(self):
        rem = MySQLConnectionRemediator('localhost', 3306, 'user', 'pass')
        mock_cursor = Mock()
        rem.connection = Mock()
        rem.connection.cursor.return_value = mock_cursor
        
        result = rem.kill_connection(101)
        
        assert result is True
        mock_cursor.execute.assert_called_once_with('KILL 101')
        mock_cursor.close.assert_called_once()

    def test_kill_connection_failure(self):
        rem = MySQLConnectionRemediator('localhost', 3306, 'user', 'pass')
        mock_cursor = Mock()
        mock_cursor.execute.side_effect = Exception('Kill failed')
        rem.connection = Mock()
        rem.connection.cursor.return_value = mock_cursor
        
        result = rem.kill_connection(101)
        
        assert result is False

    def test_remediate_with_idle_connections(self):
        rem = MySQLConnectionRemediator('localhost', 3306, 'user', 'pass')
        rem.connection = Mock()
        
        with patch.object(rem, 'get_thread_count', side_effect=[600, 550]):
            with patch.object(rem, 'get_idle_connections', return_value=[
                {'ID': 101}, {'ID': 102}
            ]):
                with patch.object(rem, 'kill_connection', return_value=True):
                    killed = rem.remediate()
        
        assert killed == 2

    def test_remediate_no_idle_connections(self):
        rem = MySQLConnectionRemediator('localhost', 3306, 'user', 'pass')
        rem.connection = Mock()
        
        with patch.object(rem, 'get_thread_count', return_value=540):
            with patch.object(rem, 'get_idle_connections', return_value=[]):
                killed = rem.remediate()
        
        assert killed == 0

    def test_close(self):
        rem = MySQLConnectionRemediator('localhost', 3306, 'user', 'pass')
        rem.connection = Mock()
        
        rem.close()
        
        rem.connection.close.assert_called_once()