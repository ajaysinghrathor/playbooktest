import pytest
from unittest.mock import Mock, MagicMock, patch, call
import sys
import pymysql

sys.path.insert(0, '/app/generated_fixes/alert-06f5ea39-eedf-4081-a376-bbc96e547c88')
from fix import MySQLThreadRemediator, THREAD_THRESHOLD, SAFE_THRESHOLD


class TestMySQLThreadRemediator:
    
    @patch('fix.pymysql.connect')
    def test_connect_success(self, mock_connect):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        
        remediator = MySQLThreadRemediator('localhost', 3306, 'user', 'pass')
        result = remediator.connect()
        
        assert result is True
        assert remediator.connection == mock_conn
        mock_connect.assert_called_once()

    @patch('fix.pymysql.connect')
    def test_connect_failure(self, mock_connect):
        mock_connect.side_effect = pymysql.OperationalError("Connection failed")
        
        remediator = MySQLThreadRemediator('localhost', 3306, 'user', 'pass')
        result = remediator.connect()
        
        assert result is False

    def test_get_thread_count(self):
        remediator = MySQLThreadRemediator('localhost', 3306, 'user', 'pass')
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {'Variable_name': 'Threads_connected', 'Value': '600'}
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        remediator.connection = mock_conn
        
        count = remediator.get_thread_count()
        
        assert count == 600
        mock_cursor.execute.assert_called_once_with("SHOW STATUS LIKE 'Threads_connected'")

    def test_get_idle_connections(self):
        remediator = MySQLThreadRemediator('localhost', 3306, 'user', 'pass')
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {'id': 100, 'user': 'app', 'host': '10.1.1.1', 'db': 'test', 'command': 'Sleep', 'time': 400, 'state': ''},
            {'id': 101, 'user': 'app', 'host': '10.1.1.2', 'db': 'test', 'command': 'Sleep', 'time': 500, 'state': ''}
        ]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        remediator.connection = mock_conn
        
        idle_conns = remediator.get_idle_connections()
        
        assert len(idle_conns) == 2
        assert idle_conns[0]['id'] == 100

    def test_kill_connection_success(self):
        remediator = MySQLThreadRemediator('localhost', 3306, 'user', 'pass')
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        remediator.connection = mock_conn
        
        result = remediator.kill_connection(100)
        
        assert result is True
        mock_cursor.execute.assert_called_once_with("KILL 100")

    def test_kill_connection_failure(self):
        remediator = MySQLThreadRemediator('localhost', 3306, 'user', 'pass')
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = pymysql.Error("Kill failed")
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        remediator.connection = mock_conn
        
        result = remediator.kill_connection(100)
        
        assert result is False

    @patch.object(MySQLThreadRemediator, 'get_thread_count')
    @patch.object(MySQLThreadRemediator, 'get_idle_connections')
    @patch.object(MySQLThreadRemediator, 'kill_connection')
    def test_remediate_below_threshold(self, mock_kill, mock_get_idle, mock_get_count):
        mock_get_count.return_value = 500
        
        remediator = MySQLThreadRemediator('localhost', 3306, 'user', 'pass')
        remediator.connection = MagicMock()
        
        result = remediator.remediate()
        
        assert result is True
        mock_get_idle.assert_not_called()
        mock_kill.assert_not_called()

    @patch.object(MySQLThreadRemediator, 'get_thread_count')
    @patch.object(MySQLThreadRemediator, 'get_idle_connections')
    @patch.object(MySQLThreadRemediator, 'kill_connection')
    def test_remediate_kills_idle_connections(self, mock_kill, mock_get_idle, mock_get_count):
        mock_get_count.side_effect = [600, 450, 380]
        mock_get_idle.return_value = [
            {'id': 100, 'user': 'app', 'time': 400},
            {'id': 101, 'user': 'app', 'time': 500}
        ]
        mock_kill.return_value = True
        
        remediator = MySQLThreadRemediator('localhost', 3306, 'user', 'pass')
        remediator.connection = MagicMock()
        
        result = remediator.remediate()
        
        assert result is True
        assert mock_kill.call_count == 2

    @patch.object(MySQLThreadRemediator, 'get_thread_count')
    @patch.object(MySQLThreadRemediator, 'get_idle_connections')
    def test_remediate_no_idle_connections(self, mock_get_idle, mock_get_count):
        mock_get_count.return_value = 600
        mock_get_idle.return_value = []
        
        remediator = MySQLThreadRemediator('localhost', 3306, 'user', 'pass')
        remediator.connection = MagicMock()
        
        result = remediator.remediate()
        
        assert result is False