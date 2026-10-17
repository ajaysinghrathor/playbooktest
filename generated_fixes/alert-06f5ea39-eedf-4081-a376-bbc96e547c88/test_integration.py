import pytest
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, 'generated_fixes/alert-06f5ea39-eedf-4081-a376-bbc96e547c88')
from fix import MySQLConnectionRemediator, main


@pytest.mark.integration
class TestMySQLRemediationIntegration:
    
    @patch('fix.pymysql.connect')
    def test_full_remediation_workflow(self, mock_connect):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        mock_cursor.fetchone.return_value = ('Threads_connected', '580')
        mock_cursor.fetchall.side_effect = [
            [{'id': 10, 'user': 'app1', 'host': '10.0.0.1', 'db': 'testdb', 'command': 'Sleep', 'time': 350, 'state': ''}],
            [{'id': 20, 'user': 'app2', 'host': '10.0.0.2', 'db': 'testdb', 'command': 'Query', 'time': 90, 'state': 'executing', 'query_preview': 'SELECT * FROM'}]
        ]
        
        remediator = MySQLConnectionRemediator('localhost', 3306, 'root', 'password', 300, 60, 10)
        remediator.connect()
        killed = remediator.remediate()
        remediator.close()
        
        assert killed == 2
        assert mock_cursor.execute.call_count >= 4
        mock_conn.close.assert_called_once()

    @patch('fix.pymysql.connect')
    def test_connection_error_handling(self, mock_connect):
        mock_connect.side_effect = Exception('Database unavailable')
        
        remediator = MySQLConnectionRemediator('localhost', 3306, 'root', 'password', 300, 60, 10)
        with pytest.raises(Exception, match='Database unavailable'):
            remediator.connect()

    @patch('fix.pymysql.connect')
    @patch('sys.argv', ['fix.py', '--host', 'testhost', '--port', '3306', '--user', 'testuser', '--password', 'testpass'])
    def test_main_success_path(self, mock_connect):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        mock_cursor.fetchone.return_value = ('Threads_connected', '560')
        mock_cursor.fetchall.side_effect = [
            [{'id': 5, 'user': 'test', 'host': '10.0.0.5', 'db': 'db', 'command': 'Sleep', 'time': 400, 'state': ''}],
            []
        ]
        
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0

    @patch('fix.pymysql.connect')
    @patch('sys.argv', ['fix.py', '--host', 'testhost', '--port', '3306', '--user', 'testuser', '--password', 'testpass'])
    def test_main_no_remediation_needed(self, mock_connect):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        mock_cursor.fetchone.return_value = ('Threads_connected', '200')
        mock_cursor.fetchall.side_effect = [[], []]
        
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 2

    @patch('fix.pymysql.connect')
    @patch('sys.argv', ['fix.py', '--host', 'badhost', '--port', '3306', '--user', 'testuser', '--password', 'testpass'])
    def test_main_connection_failure(self, mock_connect):
        mock_connect.side_effect = Exception('Connection refused')
        
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 1