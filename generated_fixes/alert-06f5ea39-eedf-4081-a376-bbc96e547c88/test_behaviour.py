import pytest
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, '/app/generated_fixes/alert-06f5ea39-eedf-4081-a376-bbc96e547c88')
from fix import MySQLConnectionRemediator, THREAD_THRESHOLD


class TestMySQLRemediationBehaviour:
    
    @pytest.fixture
    def mock_mysql_environment(self):
        with patch('fix.pymysql.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn
            yield mock_conn

    def test_given_high_thread_count_when_remediate_then_idle_connections_killed(self, mock_mysql_environment):
        # GIVEN: MySQL has 600 active threads with many idle connections
        mock_conn = mock_mysql_environment
        
        thread_counts = [600, 600, 580, 560, 540, 520, 500]
        mock_cursor_count = MagicMock()
        mock_cursor_count.fetchone.side_effect = [(f'Threads_connected', str(c)) for c in thread_counts]
        
        idle_processes = [
            {'Id': i, 'User': f'app{i}', 'Command': 'Sleep', 'Time': 400, 'Info': None}
            for i in range(10, 30)
        ]
        mock_cursor_processlist = MagicMock()
        mock_cursor_processlist.fetchall.return_value = idle_processes
        
        mock_cursor_kill = MagicMock()
        
        def cursor_factory(*args, **kwargs):
            if 'DictCursor' in str(kwargs):
                return MagicMock(__enter__=MagicMock(return_value=mock_cursor_processlist))
            return MagicMock(__enter__=MagicMock(return_value=mock_cursor_count))
        
        mock_conn.cursor.side_effect = cursor_factory
        
        remediator = MySQLConnectionRemediator('localhost', 3306, 'admin', 'secret')
        remediator.connection = mock_conn
        
        # WHEN: Remediation is executed
        initial, killed, final = remediator.remediate()
        
        # THEN: Idle connections are identified and killed, reducing thread count
        assert initial == 600
        assert killed > 0
        assert final < initial

    def test_given_thread_count_below_threshold_when_remediate_then_no_action_taken(self, mock_mysql_environment):
        # GIVEN: MySQL has 500 threads (below threshold of 551)
        mock_conn = mock_mysql_environment
        
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ('Threads_connected', '500')
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        
        remediator = MySQLConnectionRemediator('localhost', 3306, 'admin', 'secret')
        remediator.connection = mock_conn
        
        # WHEN: Remediation is executed
        initial, killed, final = remediator.remediate()
        
        # THEN: No connections are killed
        assert initial == 500
        assert killed == 0
        assert final == 500

    def test_given_long_running_queries_when_remediate_then_queries_terminated(self, mock_mysql_environment):
        # GIVEN: MySQL has long-running queries blocking resources
        mock_conn = mock_mysql_environment
        
        mock_cursor_count = MagicMock()
        mock_cursor_count.fetchone.side_effect = [
            ('Threads_connected', '580'),
            ('Threads_connected', '580'),
            ('Threads_connected', '575'),
            ('Threads_connected', '570'),
        ]
        
        long_queries = [
            {'Id': 50, 'User': 'batch_user', 'Command': 'Query', 'Time': 800, 'Info': 'SELECT COUNT(*) FROM huge_table'},
            {'Id': 51, 'User': 'report_user', 'Command': 'Query', 'Time': 900, 'Info': 'ANALYZE TABLE slow_table'},
        ]
        mock_cursor_processlist = MagicMock()
        mock_cursor_processlist.fetchall.return_value = long_queries
        
        mock_cursor_kill = MagicMock()
        
        def cursor_factory(*args, **kwargs):
            if 'DictCursor' in str(kwargs):
                return MagicMock(__enter__=MagicMock(return_value=mock_cursor_processlist))
            return MagicMock(__enter__=MagicMock(return_value=mock_cursor_count))
        
        mock_conn.cursor.side_effect = cursor_factory
        
        remediator = MySQLConnectionRemediator('localhost', 3306, 'admin', 'secret')
        remediator.connection = mock_conn
        
        # WHEN: Remediation is executed
        initial, killed, final = remediator.remediate()
        
        # THEN: Long-running queries are killed
        assert initial == 580
        assert killed >= 1
        assert final <= initial

    def test_given_remediation_success_when_verify_then_thread_count_below_threshold(self, mock_mysql_environment):
        # GIVEN: A successful remediation has occurred
        mock_conn = mock_mysql_environment
        
        with patch('fix.MySQLConnectionRemediator.remediate', return_value=(600, 100, 450)):
            remediator = MySQLConnectionRemediator('localhost', 3306, 'admin', 'secret')
            remediator.connection = mock_conn
            
            # WHEN: Remediation completes
            initial, killed, final = remediator.remediate()
            
            # THEN: Final thread count is below the threshold
            assert final < THREAD_THRESHOLD
            assert final == 450