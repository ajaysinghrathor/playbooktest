# MySQL Thread Connection Remediation

## Overview
Automated remediation for alert `DA_MYSQLDB_THREAD_CONNECTION_GTOE_551` triggered when MySQL thread connections exceed threshold (≥551). The script terminates idle connections, adjusts max_connections, and flushes thread cache to restore normal operation.

## Files
- `fix.py` - Main remediation script that connects to MySQL and performs connection cleanup
- `test_unit.py` - Unit tests with mocked MySQL interactions
- `test_integration.py` - Integration tests requiring live MySQL instance
- `test_behaviour.py` - BDD-style behaviour tests validating observable outcomes
- `run_fix.yml` - Ansible playbook wrapper to execute fix.py
- `README.md` - This documentation

## Prerequisites
- Python 3.7+
- pip packages: `pymysql>=1.0.0`
- MySQL user with `PROCESS`, `SUPER` privileges (to view processlist and kill connections)
- Network access to target MySQL instance
- For tests: `pytest>=7.0.0`, `pytest-mock>=3.10.0`

## Input Parameters

| Parameter | CLI Flag | Env Var | Required | Default | Description |
|-----------|----------|---------|----------|---------|-------------|
| MySQL Host | `--host` | `MYSQL_HOST` | Yes | - | MySQL server hostname or IP address |
| MySQL User | `--user` | `MYSQL_USER` | Yes | - | MySQL username with PROCESS and SUPER privileges |
| MySQL Password | `--password` | `MYSQL_PASSWORD` | Yes | - | MySQL user password |
| MySQL Port | `--port` | `MYSQL_PORT` | No | 3306 | MySQL server port |
| Idle Threshold | `--idle-threshold` | `MYSQL_IDLE_THRESHOLD` | No | 300 | Idle time in seconds before connection is killed |
| Max Connections | `--max-connections` | `MYSQL_MAX_CONNECTIONS` | No | 1000 | Target max_connections setting |
| Thread Threshold | `--thread-threshold` | `MYSQL_THREAD_THRESHOLD` | No | 551 | Thread count threshold to trigger remediation |
| Dry Run | `--dry-run` | `MYSQL_DRY_RUN` | No | false | Execute without making changes (logs actions only) |

## How to Run

### Local Dry-Run
```bash
python fix.py \
  --host 10.224.0.9 \
  --port 3306 \
  --user admin \
  --password 'your-password' \
  --idle-threshold 300 \
  --max-connections 1000 \
  --thread-threshold 551 \
  --dry-run
```

### Real Execution
```bash
python fix.py \
  --host 10.224.0.9 \
  --port 3306 \
  --user admin \
  --password 'your-password' \
  --idle-threshold 300 \
  --max-connections 1000 \
  --thread-threshold 551
```

### Via Ansible Playbook
```bash
ansible-playbook run_fix.yml \
  -i inventory.ini \
  -e "target_mysql_host=10.224.0.9" \
  -e "target_mysql_port=3306" \
  -e "target_mysql_user=admin" \
  -e "target_mysql_password=your-password" \
  -e "mysql_idle_threshold=300" \
  -e "mysql_max_connections_target=1000" \
  -e "mysql_thread_threshold=551" \
  -e "mysql_dry_run=false"
```

## How to Run Tests

### Install Test Dependencies
```bash
pip install pytest>=7.0.0 pytest-mock>=3.10.0 pymysql>=1.0.0
```

### Unit Tests
```bash
pytest test_unit.py -v
```

### Integration Tests
Requires live MySQL instance. Set environment variables:
```bash
export MYSQL_HOST=localhost
export MYSQL_PORT=3306
export MYSQL_USER=root
export MYSQL_PASSWORD=test_password

pytest -m integration test_integration.py -v
```

### Behaviour Tests
```bash
pytest test_behaviour.py -v
```

### All Tests
```bash
pytest -v
```

## Exit Codes
- `0` - Remediation completed successfully
- `1` - Remediation failed (connection error, permission denied, or unexpected exception)

## Rollback
- Killed connections: Clients will automatically reconnect; no rollback needed
- `max_connections` change: Persists until server restart (dynamic variable); manually revert with:
  ```sql
  SET GLOBAL max_connections = <previous_value>;
  ```
- Thread cache flush: No rollback needed (status counters reset only)
- To permanently set max_connections, update `/etc/my.cnf` or equivalent and restart MySQL