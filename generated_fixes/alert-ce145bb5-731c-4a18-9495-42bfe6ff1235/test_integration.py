import pytest
import os
import subprocess
import time
from unittest.mock import patch, MagicMock

pytestmark = pytest.mark.integration


@pytest.fixture
def mock_mysql_env():
    env = os.environ.copy()
    env['MYSQL_HOST'] = os.getenv('MYSQL_HOST', '127.0.0.1')
    env['MYSQL_PORT'] = os.getenv('MYSQL_PORT', '3306')
    env['MYSQL_USER'] = os.getenv('MYSQL_USER', 'testuser')
    env['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD', 'testpass')
    return env


@pytest.mark.integration
def test_fix_script_dry_run_execution(mock_mysql_env):
    script_path = os.path.join(os.path.dirname(__file__), 'fix.py')
    
    with patch('fix.pymysql.connect') as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.side_effect = [
            {'Value': '600'},
            {'Value': '1000'}
        ]
        mock_cursor.fetchall.side_effect = [
            [{'id': 100, 'user': 'app', 'host': 'h', 'db': 'test', 'command': 'Sleep', 'time': 400, 'state': '', 'info': None}],
            [{'id': 101, 'user': 'app', 'host': 'h', 'db': 'test', 'command': 'Query', 'time': 700, 'state': 'executing', 'info': 'SELECT'}]
        ]
        mock_connect.return_value = mock_conn
        
        result = subprocess.run(
            ['python3', script_path, '--host', 'testhost', '--port', '3306', 
             '--user', 'testuser', '--password', 'testpass', '--dry-run'],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        assert result.returncode == 0
        assert 'Remediation completed successfully' in result.stdout or 'DRY-RUN' in result.stdout


@pytest.mark.integration
def test_fix_script_with_missing_credentials():
    script_path = os.path.join(os.path.dirname(__file__), 'fix.py')
    
    result = subprocess.run(
        ['python3', script_path, '--host', 'testhost'],
        capture_output=True,
        text=True,
        timeout=10
    )
    
    assert result.returncode != 0


@pytest.mark.integration
def test_ansible_playbook_syntax():
    playbook_path = os.path.join(os.path.dirname(__file__), 'run_fix.yml')
    
    result = subprocess.run(
        ['ansible-playbook', '--syntax-check', playbook_path],
        capture_output=True,
        text=True,
        timeout=10
    )
    
    assert result.returncode == 0


@pytest.mark.integration
@patch('fix.get_connection')
@patch('fix.get_current_threads')
def test_connection_handling_failure(mock_threads, mock_conn):
    import fix
    
    mock_conn.side_effect = Exception("Connection refused")
    
    with patch('sys.argv', ['fix.py', '--host', 'badhost', '--user', 'u', '--password', 'p']):
        result = fix.main()
    
    assert result == 1


@pytest.mark.integration
@patch('fix.pymysql.connect')
def test_full_remediation_workflow_simulation(mock_connect):
    import fix
    
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    
    mock_cursor.fetchone.side_effect = [
        {'Value': '620'},
        {'Value': '1000'},
        {'Value': '570'}
    ]
    
    mock_cursor.fetchall.side_effect = [
        [{'id': i, 'user': 'app', 'host': 'host', 'db': 'db', 'command': 'Sleep', 'time': 400, 'state': '', 'info': None} for i in range(100, 150)],
        [{'id': 200, 'user': 'app', 'host': 'host', 'db': 'db', 'command': 'Query', 'time': 700, 'state': 'exec', 'info': 'SELECT * FROM table'}]
    ]
    
    mock_connect.return_value = mock_conn
    
    with patch('sys.argv', ['fix.py', '--host', 'localhost', '--user', 'admin', '--password', 'secret']):
        with patch('time.sleep'):
            result = fix.main()
    
    assert result == 0
    assert mock_cursor.execute.call_count > 0