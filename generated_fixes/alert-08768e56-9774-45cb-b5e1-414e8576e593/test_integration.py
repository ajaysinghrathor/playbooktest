import pytest
import os
import pymysql
from fix import MySQLConnectionRemediator


@pytest.fixture
def mysql_config():
    return {
        'host': os.getenv('MYSQL_HOST', 'localhost'),
        'port': int(os.getenv('MYSQL_PORT', 3306)),
        'user': os.getenv('MYSQL_USER', 'root'),
        'password': os.getenv('MYSQL_PASSWORD', 'test_password')
    }


@pytest.fixture
def live_connection(mysql_config):
    try:
        conn = pymysql.connect(**mysql_config, connect_timeout=5)
        yield conn
        conn.close()
    except Exception as e:
        pytest.skip(f"MySQL not available: {e}")


@pytest.mark.integration
def test_connect_to_live_mysql(mysql_config):
    remediator = MySQLConnectionRemediator(
        host=mysql_config['host'],
        port=mysql_config['port'],
        user=mysql_config['user'],
        password=mysql_config['password'],
        idle_threshold=300,
        max_connections=1000,
        thread_threshold=551,
        dry_run=True
    )
    try:
        remediator.connect()
        assert remediator.conn is not None
        remediator.conn.close()
    except Exception as e:
        pytest.fail(f"Failed to connect: {e}")


@pytest.mark.integration
def test_get_thread_count_live(mysql_config, live_connection):
    remediator = MySQLConnectionRemediator(
        host=mysql_config['host'],
        port=mysql_config['port'],
        user=mysql_config['user'],
        password=mysql_config['password'],
        idle_threshold=300,
        max_connections=1000,
        thread_threshold=551,
        dry_run=True
    )
    remediator.connect()
    count = remediator.get_thread_count()
    assert count >= 1
    remediator.conn.close()


@pytest.mark.integration
def test_get_max_connections_live(mysql_config, live_connection):
    remediator = MySQLConnectionRemediator(
        host=mysql_config['host'],
        port=mysql_config['port'],
        user=mysql_config['user'],
        password=mysql_config['password'],
        idle_threshold=300,
        max_connections=1000,
        thread_threshold=551,
        dry_run=True
    )
    remediator.connect()
    max_conn = remediator.get_max_connections()
    assert max_conn > 0
    remediator.conn.close()


@pytest.mark.integration
def test_dry_run_remediation_live(mysql_config, live_connection):
    remediator = MySQLConnectionRemediator(
        host=mysql_config['host'],
        port=mysql_config['port'],
        user=mysql_config['user'],
        password=mysql_config['password'],
        idle_threshold=300,
        max_connections=1000,
        thread_threshold=9999,
        dry_run=True
    )
    success, result = remediator.remediate()
    assert success is True
    assert 'initial_threads' in result
    assert result['initial_threads'] >= 1


@pytest.mark.integration
def test_get_idle_connections_live(mysql_config, live_connection):
    remediator = MySQLConnectionRemediator(
        host=mysql_config['host'],
        port=mysql_config['port'],
        user=mysql_config['user'],
        password=mysql_config['password'],
        idle_threshold=0,
        max_connections=1000,
        thread_threshold=551,
        dry_run=True
    )
    remediator.connect()
    idle = remediator.get_idle_connections()
    assert isinstance(idle, list)
    remediator.conn.close()