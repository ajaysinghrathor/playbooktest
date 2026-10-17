import pytest
from unittest.mock import patch, Mock
import sys
sys.path.insert(0, '.')
from fix import MySQLConnectionRemediator


@pytest.mark.behaviour
class TestMySQLRemediationBehaviour:
    
    @patch('fix.pymysql.connect')
    def test_given_high_thread_count_when_remediate_then_idle_connections_killed(self, mock_connect):
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        mock_cursor.fetchone.side_effect = [
            ('Threads_connected', '580'),
            ('Threads_connected', '540')
        ]
        mock_cursor.fetchall.return_value = [
            {'ID': 201, 'USER': 'app1', 'HOST': '10.1.1.1', 'COMMAND': 'Sleep', 'TIME': 350, 'STATE': '', 'INFO': None, 'DB': 'testdb'},
            {'ID': 202, 'USER': 'app2', 'HOST': '10.1.1.2', 'COMMAND': 'Sleep', 'TIME': 400, 'STATE': '', 'INFO': None, 'DB': 'testdb'}
        ]
        
        remediator = MySQLConnectionRemediator('10.244.5.1', 3306, 'admin', 'password', 300, 100)
        remediator.connect()
        
        initial_count = remediator.get_thread_count()
        assert initial_count == 580
        
        killed_count = remediator.remediate()
        
        assert killed_count == 2
        kill_calls = [call for call in mock_cursor.execute.call_args_list if 'KILL' in str(call)]
        assert len(kill_calls) == 2
        
        remediator.close()

    @patch('fix.pymysql.connect')
    def test_given_no_idle_connections_when_remediate_then_no_kills_executed(self, mock_connect):
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        mock_cursor.fetchone.return_value = ('Threads_connected', '540')
        mock_cursor.fetchall.return_value = []
        
        remediator = MySQLConnectionRemediator('10.244.5.1', 3306, 'admin', 'password')
        remediator.connect()
        
        killed_count = remediator.remediate()
        
        assert killed_count == 0
        kill_calls = [call for call in mock_cursor.execute.call_args_list if 'KILL' in str(call)]
        assert len(kill_calls) == 0
        
        remediator.close()

    @patch('fix.pymysql.connect')
    def test_given_connection_failure_when_connect_then_exception_raised(self, mock_connect):
        mock_connect.side_effect = Exception('Connection timeout')
        
        remediator = MySQLConnectionRemediator('invalid-host', 3306, 'user', 'pass')
        
        with pytest.raises(Exception, match='Connection timeout'):
            remediator.connect()

    @patch('fix.pymysql.connect')
    def test_given_max_kill_limit_when_remediate_then_respects_limit(self, mock_connect):
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        mock_cursor.fetchone.side_effect = [
            ('Threads_connected', '610'),
            ('Threads_connected', '595')
        ]
        
        idle_connections = [{'ID': i, 'USER': f'app{i}', 'TIME': 400} for i in range(1, 21)]
        mock_cursor.fetchall.return_value = idle_connections[:15]
        
        remediator = MySQLConnectionRemediator('10.244.5.1', 3306, 'admin', 'password', 300, 15)
        remediator.connect()
        
        killed_count = remediator.remediate()
        
        assert killed_count == 15
        
        remediator.close()