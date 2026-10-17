import pytest
import sys
from unittest.mock import Mock, MagicMock, patch, call
from io import StringIO

sys.path.insert(0, '.')
from fix import MySQLConnectionRemediator


class TestMySQLConnectionRemediator:
    
    @patch('fix.pymysql.connect')
    def test_connect_success(self, mock_connect):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        
        remediator = MySQLConnectionRemediator('localhost', 3306, 'user', 'pass', 300, 551)
        remediator.connect()
        
        assert remediator.connection == mock_conn
        mock_connect.assert_called_once()

    @patch('fix.pymysql.connect')
    def test_connect_failure(self, mock_connect):
        mock_connect.side_effect = Exception("Connection failed")
        
        remediator = MySQLConnectionRemediator('localhost', 3306, 'user', 'pass', 300, 551)
        
        with pytest.raises(Exception, match="Connection failed"):
            remediator.connect()

    def test_get_thread_count(self):
        remediator = MySQLConnectionRemediator('localhost', 3306, 'user', 'pass', 300, 551)
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ('Threads_connected', '600')
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        remediator.connection = mock_conn
        
        count = remediator.get_thread_count()
        
        assert count == 600
        mock_cursor.execute.assert_called_once()

    def test_get_idle_connections(self):
        remediator = MySQLConnectionRemediator('localhost', 3306, 'user', 'pass', 300, 551)
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {'ID': 123, 'USER': 'app', 'TIME': 400},
            {'ID': 456, 'USER': 'app', 'TIME': 350}
        ]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        remediator.connection = mock_conn
        
        conns = remediator.get_idle_connections()
        
        assert len(conns) == 2
        assert conns[0]['ID'] == 123

    def test_kill_connection_success(self):
        remediator = MySQLConnectionRemediator('localhost', 3306, 'user', 'pass', 300, 551)
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        remediator.connection = mock_conn
        
        result = remediator.kill_connection(123)
        
        assert result is True
        mock_cursor.execute.assert_called_with('KILL 123')

    def test_kill_connection_failure(self):
        remediator = MySQLConnectionRemediator('localhost', 3306, 'user', 'pass', 300, 551)
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("Kill failed")
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        remediator.connection = mock_conn
        
        result = remediator.kill_connection(123)
        
        assert result is False

    @patch('fix.time.sleep')
    def test_remediate_below_threshold(self, mock_sleep):
        remediator = MySQLConnectionRemediator('localhost', 3306, 'user', 'pass', 300, 551)
        remediator.connection = MagicMock()
        remediator.get_thread_count = Mock(return_value=500)
        
        exit_code = remediator.remediate()
        
        assert exit_code == 0

    @patch('fix.time.sleep')
    def test_remediate_success(self, mock_sleep):
        remediator = MySQLConnectionRemediator('localhost', 3306, 'user', 'pass', 300, 551)
        remediator.connection = MagicMock()
        remediator.get_thread_count = Mock(side_effect=[600, 500])
        remediator.get_idle_connections = Mock(return_value=[
            {'ID': 123, 'USER': 'app', 'TIME': 400}
        ])
        remediator.kill_connection = Mock(return_value=True)
        
        exit_code = remediator.remediate()
        
        assert exit_code == 0
        remediator.kill_connection.assert_called_with(123)

    @patch('fix.time.sleep')
    def test_remediate_still_above_threshold(self, mock_sleep):
        remediator = MySQLConnectionRemediator('localhost', 3306, 'user', 'pass', 300, 551)
        remediator.connection = MagicMock()
        remediator.get_thread_count = Mock(side_effect=[600, 600])
        remediator.get_idle_connections = Mock(return_value=[
            {'ID': 123, 'USER': 'app', 'TIME': 400}
        ])
        remediator.kill_connection = Mock(return_value=True)
        
        exit_code = remediator.remediate()
        
        assert exit_code == 1