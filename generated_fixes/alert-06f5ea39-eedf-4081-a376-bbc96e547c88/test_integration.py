import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, '/app/generated_fixes/alert-06f5ea39-eedf-4081-a376-bbc96e547c88')
from fix import MySQLConnectionRemediator, main


@pytest.mark.integration
class TestMySQLRemediationIntegration:
    
    @patch('fix.pymysql.connect')
    def test_full_remediation_workflow(self, mock_connect):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        
        mock_cursor_count = MagicMock()
        mock_cursor_count.fetchone.side_effect = [
            ('Threads_connected', '600'),
            ('Threads_connected', '600'),
            ('Threads_connected', '580'),
            ('Threads_connected', '560'),
            ('Threads_connected', '540'),
        ]
        
        mock_cursor_processlist = MagicMock()
        mock_cursor_processlist.fetchall.return_value = [
            {'Id': 10, 'User': 'app1', 'Command': 'Sleep', 'Time': 400, 'Info': None},
            {'Id': 11, 'User': 'app2', 'Command': 'Sleep', 'Time': 350, 'Info': None},
            {'Id': 12, 'User': 'app3', 'Command': 'Query', 'Time': 700, 'Info': 'SELECT * FROM large_table'},
        ]
        
        mock_cursor_kill = MagicMock()
        
        def cursor_side_effect(*args, **kwargs):
            if 'DictCursor' in str(kwargs):
                return MagicMock(__enter__=MagicMock(return_value=mock_cursor_processlist))
            return MagicMock(__enter__=MagicMock(return_value=mock_cursor_count if not hasattr(cursor_side_effect, 'kill_mode') else mock_cursor_kill))
        
        mock_conn.cursor.side_effect = cursor_side_effect
        
        remediator = MySQLConnectionRemediator(
            host='test-host',
            port=3306,
            user='test-user',
            password='test-pass'
        )
        
        remediator.connect()
        initial, killed, final = remediator.remediate()
        
        assert initial >= 0
        assert killed >= 0
        assert final >= 0
        remediator.close()

    @patch('fix.pymysql.connect')
    @patch('sys.argv', ['fix.py', '--host', 'localhost', '--port', '3306', '--user', 'admin', '--password', 'secret'])
    def test_main_success(self, mock_connect):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [
            ('Threads_connected', '600'),
            ('Threads_connected', '400'),
        ]
        mock_cursor.fetchall.return_value = [
            {'Id': 1, 'User': 'app', 'Command': 'Sleep', 'Time': 400, 'Info': None},
        ]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        
        with patch('fix.MySQLConnectionRemediator.remediate', return_value=(600, 50, 400)):
            exit_code = main()
            assert exit_code == 0

    @patch('fix.pymysql.connect')
    @patch('sys.argv', ['fix.py', '--host', 'localhost', '--user', 'admin', '--password', 'secret'])
    def test_main_connection_failure(self, mock_connect):
        mock_connect.side_effect = Exception('Connection refused')
        
        exit_code = main()
        assert exit_code == 1

    @patch('fix.pymysql.connect')
    @patch('sys.argv', ['fix.py', '--host', 'localhost', '--user', 'admin', '--password', 'secret'])
    def test_main_remediation_insufficient(self, mock_connect):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        
        with patch('fix.MySQLConnectionRemediator.remediate', return_value=(650, 20, 630)):
            exit_code = main()
            assert exit_code == 1