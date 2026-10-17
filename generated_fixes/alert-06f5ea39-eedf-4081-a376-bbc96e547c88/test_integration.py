import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, '.')
from fix import MySQLConnectionRemediator, main


@pytest.mark.integration
class TestMySQLConnectionRemediatorIntegration:
    
    @patch('fix.pymysql.connect')
    def test_full_remediation_workflow(self, mock_connect):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [
            ('Threads_connected', '600'),
            ('Threads_connected', '500')
        ]
        mock_cursor.fetchall.return_value = [
            {'ID': 100, 'USER': 'app1', 'HOST': 'host1', 'DB': 'db1', 'COMMAND': 'Sleep', 'TIME': 400, 'STATE': '', 'INFO': None},
            {'ID': 101, 'USER': 'app2', 'HOST': 'host2', 'DB': 'db2', 'COMMAND': 'Sleep', 'TIME': 350, 'STATE': '', 'INFO': None}
        ]
        
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        remediator = MySQLConnectionRemediator('testhost', 3306, 'testuser', 'testpass', 300, 551)
        remediator.connect()
        exit_code = remediator.remediate()
        remediator.close()
        
        assert exit_code == 0
        assert mock_cursor.execute.call_count >= 3

    @patch('fix.pymysql.connect')
    def test_no_idle_connections(self, mock_connect):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ('Threads_connected', '600')
        mock_cursor.fetchall.return_value = []
        
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        remediator = MySQLConnectionRemediator('testhost', 3306, 'testuser', 'testpass', 300, 551)
        remediator.connect()
        exit_code = remediator.remediate()
        remediator.close()
        
        assert exit_code == 1

    @patch('fix.pymysql.connect')
    @patch('sys.argv', ['fix.py', '--host', 'localhost', '--user', 'root', '--password', 'secret'])
    def test_main_execution(self, mock_connect):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [
            ('Threads_connected', '600'),
            ('Threads_connected', '500')
        ]
        mock_cursor.fetchall.return_value = [
            {'ID': 200, 'USER': 'app', 'HOST': 'host', 'DB': 'db', 'COMMAND': 'Sleep', 'TIME': 400, 'STATE': '', 'INFO': None}
        ]
        
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        with pytest.raises(SystemExit) as exc_info:
            main()
        
        assert exc_info.value.code == 0

    @patch('fix.pymysql.connect')
    def test_connection_failure_handling(self, mock_connect):
        mock_connect.side_effect = Exception("Network unreachable")
        
        remediator = MySQLConnectionRemediator('badhost', 3306, 'user', 'pass', 300, 551)
        
        with pytest.raises(Exception, match="Network unreachable"):
            remediator.connect()