import pytest
from unittest.mock import MagicMock, patch
import sys

sys.path.insert(0, 'generated_fixes/alert-06f5ea39-eedf-4081-a376-bbc96e547c88')
from fix import MySQLConnectionRemediator


class TestMySQLRemediationBehaviour:
    
    @pytest.fixture
    def given_mysql_with_high_thread_count(self):
        remediator = MySQLConnectionRemediator('10.244.5.1', 3306, 'admin', 'secret', 300, 60, 50)
        mock_conn = MagicMock()
        remediator.connection = mock_conn
        
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = ('Threads_connected', '570')
        
        return remediator, mock_cursor

    def test_given_high_threads_when_idle_connections_exist_then_they_are_killed(self, given_mysql_with_high_thread_count):
        remediator, mock_cursor = given_mysql_with_high_thread_count
        
        idle_connections = [
            {'id': 100, 'user': 'app', 'host': '10.0.1.1', 'db': 'deposite', 'command': 'Sleep', 'time': 500, 'state': ''},
            {'id': 101, 'user': 'app', 'host': '10.0.1.2', 'db': 'deposite', 'command': 'Sleep', 'time': 450, 'state': ''}
        ]
        mock_cursor.fetchall.side_effect = [idle_connections, []]
        
        with patch.object(remediator, 'kill_connection', return_value=True) as mock_kill:
            killed = remediator.remediate()
            
            assert killed == 2
            mock_kill.assert_any_call(100)
            mock_kill.assert_any_call(101)

    def test_given_high_threads_when_long_queries_exist_then_they_are_killed(self, given_mysql_with_high_thread_count):
        remediator, mock_cursor = given_mysql_with_high_thread_count
        
        long_queries = [
            {'id': 200, 'user': 'app', 'host': '10.0.2.1', 'db': 'deposite', 'command': 'Query', 'time': 150, 'state': 'executing', 'query_preview': 'SELECT'}
        ]
        mock_cursor.fetchall.side_effect = [[], long_queries]
        
        with patch.object(remediator, 'kill_connection', return_value=True) as mock_kill:
            killed = remediator.remediate()
            
            assert killed == 1
            mock_kill.assert_called_with(200)

    def test_given_remediation_when_max_kills_reached_then_stop_killing(self, given_mysql_with_high_thread_count):
        remediator, mock_cursor = given_mysql_with_high_thread_count
        remediator.max_kills = 2
        
        idle_connections = [
            {'id': i, 'user': 'app', 'host': f'10.0.0.{i}', 'db': 'db', 'command': 'Sleep', 'time': 400, 'state': ''}
            for i in range(1, 10)
        ]
        mock_cursor.fetchall.side_effect = [idle_connections, []]
        
        with patch.object(remediator, 'kill_connection', return_value=True) as mock_kill:
            killed = remediator.remediate()
            
            assert killed == 2
            assert mock_kill.call_count == 2

    def test_given_remediation_when_no_problematic_connections_then_nothing_killed(self, given_mysql_with_high_thread_count):
        remediator, mock_cursor = given_mysql_with_high_thread_count
        
        mock_cursor.fetchall.side_effect = [[], []]
        
        with patch.object(remediator, 'kill_connection') as mock_kill:
            killed = remediator.remediate()
            
            assert killed == 0
            mock_kill.assert_not_called()

    def test_given_connection_kill_when_operation_fails_then_continue_with_next(self, given_mysql_with_high_thread_count):
        remediator, mock_cursor = given_mysql_with_high_thread_count
        
        idle_connections = [
            {'id': 300, 'user': 'app', 'host': '10.0.3.1', 'db': 'db', 'command': 'Sleep', 'time': 600, 'state': ''},
            {'id': 301, 'user': 'app', 'host': '10.0.3.2', 'db': 'db', 'command': 'Sleep', 'time': 500, 'state': ''}
        ]
        mock_cursor.fetchall.side_effect = [idle_connections, []]
        
        with patch.object(remediator, 'kill_connection', side_effect=[False, True]) as mock_kill:
            killed = remediator.remediate()
            
            assert killed == 1
            assert mock_kill.call_count == 2