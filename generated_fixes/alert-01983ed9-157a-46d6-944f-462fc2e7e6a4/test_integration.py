#!/usr/bin/env python3
import pytest
import os
import requests
from argparse import Namespace
from fix import PasswordResetServiceRemediator

@pytest.fixture
def integration_args():
    service_endpoint = os.getenv('SERVICE_ENDPOINT', 'https://ah-password-reset.internal.nl/api')
    api_key = os.getenv('API_KEY', '')
    
    return Namespace(
        service_endpoint=service_endpoint,
        service_name='ah-password-reset-service',
        business_service='AH1432AP305-01',
        region='NL',
        api_key=api_key,
        timeout=30,
        max_retries=2,
        dry_run=False
    )

@pytest.mark.integration
def test_service_endpoint_reachable(integration_args):
    rem = PasswordResetServiceRemediator(integration_args)
    try:
        response = requests.get(f"{rem.service_endpoint}/health", timeout=10)
        assert response.status_code in [200, 503], "Service endpoint should be reachable"
    except requests.exceptions.RequestException as e:
        pytest.skip(f"Service endpoint not reachable: {e}")

@pytest.mark.integration
def test_check_service_health_integration(integration_args):
    rem = PasswordResetServiceRemediator(integration_args)
    health = rem.check_service_health()
    assert isinstance(health, dict), "Health check should return a dictionary"
    assert 'status' in health, "Health response should contain status"

@pytest.mark.integration
def test_verify_backend_integration_live(integration_args):
    rem = PasswordResetServiceRemediator(integration_args)
    result = rem.verify_backend_integration()
    assert isinstance(result, bool), "Integration check should return boolean"

@pytest.mark.integration
def test_dry_run_remediation(integration_args):
    integration_args.dry_run = True
    rem = PasswordResetServiceRemediator(integration_args)
    exit_code = rem.remediate()
    assert exit_code == 0, "Dry run remediation should succeed"

@pytest.mark.integration
def test_api_authentication(integration_args):
    if not integration_args.api_key:
        pytest.skip("API key not provided for authentication test")
    
    rem = PasswordResetServiceRemediator(integration_args)
    assert 'Authorization' in rem.session.headers, "API key should be set in session headers"
    assert rem.session.headers['Authorization'] == f"Bearer {integration_args.api_key}"

@pytest.mark.integration
def test_timeout_handling(integration_args):
    integration_args.timeout = 1
    integration_args.service_endpoint = 'https://10.255.255.1/api'
    rem = PasswordResetServiceRemediator(integration_args)
    health = rem.check_service_health()
    assert health['status'] == 'unhealthy', "Should handle timeout gracefully"