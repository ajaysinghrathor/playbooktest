import pytest
import sys
from unittest.mock import patch, MagicMock
sys.path.insert(0, '/app/generated_fixes/alert-06f5ea39-eedf-4081-a376-bbc96e547c88')

from fix import MySQLConnectionRemediator


@pytest.fixture
def mock_mysql():
    mock_conn = MagicMock()
    cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = cursor
    with patch('fix.pymysql.connect', return_value=mock_conn):
        yield mock_conn, cursor


def test_given_threads_below_threshold_when_remediate_then_no_connections_killed(mock_mysql):
    mock_conn, cursor = mock_mysql
    
    cursor.fetchone.return_value = {'Value': '400'}
    
    remediator = MySQLConnectionRemediator('host', 3306, 'user', 'pass', 551, 300)
    remediator.connect()
    
    final_count, killed = remediator.remediate()
    
    assert final_count == 400
    assert killed == 0
    assert cursor.execute.call_count == 1


def test_given_threads_exceed_threshold_and_idle_connections_exist_when_remediate_then_idle_connections_killed(mock_mysql):
    mock_conn, cursor = mock_mysql
    
    cursor.fetchone.side_effect = [
        {'Value': '650'},
        {'Value': '650'},
        {'Value': '550'},
        {'Value': '545'}
    ]
    cursor.fetchall.return_value = [
        {'id': 20, 'user': 'app', 'host': 'host1', 'db': 'db', 'command': 'Sleep', 'time': 450, 'state': '', 'info': None},
        {'id': 21, 'user': 'app', 'host': 'host2', 'db': 'db', 'command': 'Sleep', 'time': 600, 'state': '', 'info': None}
    ]
    
    remediator = MySQLConnectionRemediator('host', 3306, 'user', 'pass', 551, 300)
    remediator.connect()
    
    final_count, killed = remediator.remediate()
    
    assert killed == 2
    assert final_count <= 551
    kill_calls = [call for call in cursor.execute.call_args_list if 'KILL' in str(call)]
    assert len(kill_calls) == 2


def test_given_threads_exceed_threshold_when_remediate_then_thread_count_reduces(mock_mysql):
    mock_conn, cursor = mock_mysql
    
    initial_threads = 700
    cursor.fetchone.side_effect = [
        {'Value': str(initial_threads)},
        {'Value': str(initial_threads)},
        {'Value': '540'}
    ]
    cursor.fetchall.return_value = [
        {'id': 30, 'user': 'app', 'host': 'h1', 'db': 'db', 'command': 'Sleep', 'time': 400, 'state': '', 'info': None}
    ]
    
    remediator = MySQLConnectionRemediator('host', 3306, 'user', 'pass', 551, 300)
    remediator.connect()
    
    final_count, killed = remediator.remediate()
    
    assert final_count < initial_threads
    assert killed >= 1


def test_given_no_idle_connections_when_remediate_then_no_kills_attempted(mock_mysql):
    mock_conn, cursor = mock_mysql
    
    cursor.fetchone.side_effect = [
        {'Value': '600'},
        {'Value': '600'},
        {'Value': '600'}
    ]
    cursor.fetchall.return_value = []
    
    remediator = MySQLConnectionRemediator('host', 3306, 'user', 'pass', 551, 300)
    remediator.connect()
    
    final_count, killed = remediator.remediate()
    
    assert killed == 0
    kill_calls = [call for call in cursor.execute.call_args_list if 'KILL' in str(call)]
    assert len(kill_calls) == 0


def test_given_remediation_completes_when_threshold_met_then_stops_killing(mock_mysql):
    mock_conn, cursor = mock_mysql
    
    cursor.fetchone.side_effect = [
        {'Value': '650'},
        {'Value': '650'},
        {'Value': '545'},
        {'Value': '545'}
    ]
    cursor.fetchall.return_value = [
        {'id': 40, 'user': 'app', 'host': 'h1', 'db': 'db', 'command': 'Sleep', 'time': 400, 'state': '', 'info': None},
        {'id': 41, 'user': 'app', 'host': 'h2', 'db': 'db', 'command': 'Sleep', 'time': 500, 'state': '', 'info': None},
        {'id': 42, 'user': 'app', 'host': 'h3', 'db': 'db', 'command': 'Sleep', 'time': 350, 'state': '', 'info': None}
    ]
    
    remediator = MySQLConnectionRemediator('host', 3306, 'user', 'pass', 551, 300)
    remediator.connect()
    
    final_count, killed = remediator.remediate()
    
    assert final_count <= 551
    assert killed == 1


def test_given_connection_established_when_close_then_connection_closed(mock_mysql):
    mock_conn, cursor = mock_mysql
    
    remediator = MySQLConnectionRemediator('host', 3306, 'user', 'pass', 551, 300)
    remediator.connect()
    
    remediator.close()
    
    mock_conn.close.assert_called_once()