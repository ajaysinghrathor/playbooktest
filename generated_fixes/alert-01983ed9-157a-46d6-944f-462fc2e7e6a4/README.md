# AH Password Reset Service Remediation

## Overview
Automated remediation for AH password reset service failures (Sev2 alert INC003457063). Fixes application-layer failures preventing self-service password resets for business service AH1432AP305-01 in NL region by restarting backend services and validating integration health.

## Files
- `fix.py` - Main remediation script that restarts password reset service and validates health
- `test_unit.py` - Unit tests with mocked dependencies
- `test_integration.py` - Integration tests requiring live service endpoints
- `test_behaviour.py` - Behaviour-driven tests validating observable outcomes
- `run_fix.yml` - Ansible playbook wrapper for executing the fix
- `README.md` - This documentation file

## Prerequisites
- Python 3.7+
- pip packages: `requests>=2.28.0`
- Network access to password reset service API endpoints
- Valid API key for service authentication (if required)
- Permissions to restart services and query health endpoints

## Input Parameters

| Parameter | CLI Flag | Env Variable | Required | Default | Description |
|-----------|----------|--------------|----------|---------|-------------|
| Service Endpoint | `--service-endpoint` | `SERVICE_ENDPOINT` | Yes | - | Password reset service API endpoint URL |
| Service Name | `--service-name` | `SERVICE_NAME` | Yes | - | Name of the password reset service |
| Business Service | `--business-service` | `BUSINESS_SERVICE` | Yes | - | Business service identifier (e.g., AH1432AP305-01) |
| Region | `--region` | `REGION` | Yes | - | Region code (e.g., NL) |
| API Key | `--api-key` | `API_KEY` | No | - | API authentication key for service endpoints |
| Timeout | `--timeout` | `TIMEOUT` | No | 60 | HTTP request timeout in seconds |
| Max Retries | `--max-retries` | `MAX_RETRIES` | No | 3 | Maximum retry attempts for service health checks |
| Dry Run | `--dry-run` | `DRY_RUN` | No | false | Run in dry-run mode without making changes |

## How to Run

### Local Dry Run
```bash
python3 fix.py \
  --service-endpoint "https://ah-password-reset.internal.nl/api" \
  --service-name "ah-password-reset-service" \
  --business-service "AH1432AP305-01" \
  --region "NL" \
  --api-key "your-api-key" \
  --dry-run
```

### Real Execution
```bash
python3 fix.py \
  --service-endpoint "https://ah-password-reset.internal.nl/api" \
  --service-name "ah-password-reset-service" \
  --business-service "AH1432AP305-01" \
  --region "NL" \
  --api-key "your-api-key"
```

### Via Ansible
```bash
ansible-playbook run_fix.yml -i inventory.ini \
  -e "service_endpoint=https://ah-password-reset.internal.nl/api" \
  -e "service_name=ah-password-reset-service" \
  -e "business_service=AH1432AP305-01" \
  -e "region=NL" \
  -e "api_key=your-api-key"
```

For dry-run via Ansible:
```bash
ansible-playbook run_fix.yml -i inventory.ini \
  -e "service_endpoint=https://ah-password-reset.internal.nl/api" \
  -e "service_name=ah-password-reset-service" \
  -e "business_service=AH1432AP305-01" \
  -e "region=NL" \
  -e "api_key=your-api-key" \
  -e "dry_run=true"
```

## How to Run Tests

### Install test dependencies
```bash
pip install pytest pytest-mock requests
```

### Run unit tests
```bash
pytest test_unit.py -v
```

### Run integration tests
```bash
export SERVICE_ENDPOINT="https://ah-password-reset.internal.nl/api"
export API_KEY="your-api-key"
pytest -m integration test_integration.py -v
```

### Run behaviour tests
```bash
pytest test_behaviour.py -v
```

### Run all tests
```bash
pytest -v
```

## Exit Codes
- `0` - Remediation successful
- `1` - Service restart failed
- `2` - Service did not become ready after restart
- `3` - Backend integration check failed
- `4` - Password reset flow test failed
- `99` - Unexpected error

## Rollback
The script performs read-only health checks before attempting remediation. If service restart fails, the service state remains unchanged. To rollback after a successful restart:
1. Check service logs for pre-restart state
2. Manually restart the service to previous configuration if needed
3. Contact service owners for rollback procedures specific to your environment

No data is modified; only service processes are restarted. Service configuration remains unchanged.