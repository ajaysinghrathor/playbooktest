import pytest
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, '.')
from fix import MySQLConnectionRemediator


@pytest.mark.behaviour
class TestMySQLConnectionRemediationBehaviour:
    
    @patch('fix.pymysql.connect')
    @patch('fix.time.sleep')
    def test_given_high_thread_count_when_idle_connections_exist_then_remediation_succeeds(self, mock_sleep, mock_connect):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [
            ('Threads_connected', '650'),
            ('Threads_connected', '480')
        ]
        mock_cursor.fetchall.return_value = [
            {'ID': 1001, 'USER': 'webapp', 'HOST': '10.0.1.5', 'DB': 'appdb', 'COMMAND': 'Sleep', 'TIME': 500, 'STATE': '', 'INFO': None},
            {'ID': 1002, 'USER': 'webapp', 'HOST': '10.0.1.6', 'DB': 'appdb', 'COMMAND': 'Sleep', 'TIME': 450, 'STATE': '', 'INFO': None},
            {'ID': 1003, 'USER': 'webapp', 'HOST': '10.0.1.7', 'DB': 'appdb', 'COMMAND': 'Sleep', 'TIME': 320, 'STATE': '', 'INFO': None}
        ]
        
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        remediator = MySQLConnectionRemediator('10.244.5.1', 3306, 'admin', 'password', 300, 551)
        remediator.connect()
        exit_code = remediator.remediate()
        
        assert exit_code == 0
        kill_calls = [call for call in mock_cursor.execute.call_args_list if 'KILL' in str(call)]
        assert len(kill_calls) == 3

    @patch('fix.pymysql.connect')
    def test_given_thread_count_below_threshold_when_checked_then_no_action_taken(self, mock_connect):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ('Threads_connected', '400')
        
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        remediator = MySQLConnectionRemediator('10.244.5.1', 3306, 'admin', 'password', 300, 551)
        remediator.connect()
        exit_code = remediator.remediate()
        
        assert exit_code == 0
        kill_calls = [call for call in mock_cursor.execute.call_args_list if 'KILL' in str(call)]
        assert len(kill_calls) == 0

    @patch('fix.pymysql.connect')
    @patch('fix.time.sleep')
    def test_given_high_thread_count_when_no_idle_connections_then_remediation_fails(self, mock_sleep, mock_connect):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ('Threads_connected', '700')
        mock_cursor.fetchall.return_value = []
        
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        remediator = MySQLConnectionRemediator('10.244.5.1', 3306, 'admin', 'password', 300, 551)
        remediator.connect()
        exit_code = remediator.remediate()
        
        assert exit_code == 1

    @patch('fix.pymysql.connect')
    @patch('fix.time.sleep')
    def test_given_remediation_when_thread_count_still_high_then_failure_reported(self, mock_sleep, mock_connect):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [
            ('Threads_connected', '650'),
            ('Threads_connected', '640')
        ]
        mock_cursor.fetchall.return_value = [
            {'ID': 2001, 'USER': 'app', 'HOST': '10.0.2.1', 'DB': 'db', 'COMMAND': 'Sleep', 'TIME': 400, 'STATE': '', 'INFO': None}
        ]
        
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        remediator = MySQLConnectionRemediator('10.244.5.1', 3306, 'admin', 'password', 300, 551)
        remediator.connect()
        exit_code = remediator.remediate()
        
        assert exit_code == 1

    @patch('fix.pymysql.connect')
    def test_given_database_unreachable_when_connecting_then_exception_raised(self, mock_connect):
        mock_connect.side_effect = Exception("Can't connect to MySQL server")
        
        remediator = MySQLConnectionRemediator('unreachable.host', 3306, 'admin', 'password', 300, 551)
        
        with pytest.raises(Exception, match="Can't connect to MySQL server"):
            remediator.connect()