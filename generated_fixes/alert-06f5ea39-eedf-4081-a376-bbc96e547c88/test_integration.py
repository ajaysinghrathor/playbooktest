import pytest
import pymysql
from unittest.mock import patch, Mock
import sys
sys.path.insert(0, '.')
from fix import MySQLConnectionRemediator, main


@pytest.mark.integration
class TestMySQLConnectionRemediatorIntegration:
    
    @patch('fix.pymysql.connect')
    def test_full_remediation_workflow(self, mock_connect):
        mock_conn = Mock()
        mock_cursor = Mock()
        
        mock_cursor.fetchone.side_effect = [
            ('Threads_connected', '600'),
            ('Threads_connected', '550')
        ]
        mock_cursor.fetchall.return_value = [
            {'ID': 101, 'USER': 'app', 'HOST': '10.1.1.1', 'TIME': 350},
            {'ID': 102, 'USER': 'app', 'HOST': '10.1.1.2', 'TIME': 400}
        ]
        
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        rem = MySQLConnectionRemediator('10.244.5.1', 3306, 'admin', 'secret', 300, 100)
        rem.connect()
        killed = rem.remediate()
        rem.close()
        
        assert killed == 2
        assert mock_cursor.execute.call_count >= 4
        mock_conn.close.assert_called_once()

    @patch('fix.pymysql.connect')
    def test_connection_error_handling(self, mock_connect):
        mock_connect.side_effect = pymysql.OperationalError('Connection refused')
        
        rem = MySQLConnectionRemediator('invalid-host', 3306, 'user', 'pass')
        
        with pytest.raises(pymysql.OperationalError):
            rem.connect()

    @patch('fix.pymysql.connect')
    @patch('sys.argv', ['fix.py', '--host', '10.244.5.1', '--port', '3306', 
                        '--user', 'admin', '--password', 'secret'])
    def test_main_function_success(self, mock_connect):
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.fetchone.side_effect = [
            ('Threads_connected', '600'),
            ('Threads_connected', '550')
        ]
        mock_cursor.fetchall.return_value = [
            {'ID': 101, 'USER': 'app', 'TIME': 350}
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        with pytest.raises(SystemExit) as exc_info:
            main()
        
        assert exc_info.value.code == 0

    @patch('fix.pymysql.connect')
    @patch('sys.argv', ['fix.py', '--host', '10.244.5.1', '--port', '3306',
                        '--user', 'admin', '--password', 'secret'])
    def test_main_function_failure(self, mock_connect):
        mock_connect.side_effect = Exception('DB error')
        
        with pytest.raises(SystemExit) as exc_info:
            main()
        
        assert exc_info.value.code == 1