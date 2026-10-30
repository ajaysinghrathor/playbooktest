#!/usr/bin/env python3
import pytest
from unittest.mock import patch, Mock
from argparse import Namespace
from fix import PasswordResetServiceRemediator

@pytest.fixture
def behaviour_args():
    return Namespace(
        service_endpoint='https://test.example.com/api',
        service_name='test-service',
        business_service='AH1432AP305-01',
        region='NL',
        api_key='test-key',
        timeout=30,
        max_retries=2,
        dry_run=False
    )

def test_given_unhealthy_service_when_remediate_then_service_restarted(behaviour_args):
    # GIVEN an unhealthy password reset service
    rem = PasswordResetServiceRemediator(behaviour_args)
    
    with patch.object(rem, 'check_service_health') as mock_health:
        with patch.object(rem, 'restart_service') as mock_restart:
            with patch.object(rem, 'wait_for_service_ready') as mock_wait:
                with patch.object(rem, 'verify_backend_integration') as mock_verify:
                    with patch.object(rem, 'test_password_reset_flow') as mock_test:
                        mock_health.return_value = {'status': 'unhealthy'}
                        mock_restart.return_value = True
                        mock_wait.return_value = True
                        mock_verify.return_value = True
                        mock_test.return_value = True
                        
                        # WHEN remediation is executed
                        exit_code = rem.remediate()
                        
                        # THEN service is restarted and validated
                        assert exit_code == 0
                        mock_restart.assert_called_once()
                        mock_wait.assert_called_once()
                        mock_verify.assert_called_once()
                        mock_test.assert_called_once()

def test_given_healthy_service_when_remediate_then_no_restart_needed(behaviour_args):
    # GIVEN a healthy password reset service
    rem = PasswordResetServiceRemediator(behaviour_args)
    
    with patch.object(rem, 'check_service_health') as mock_health:
        with patch.object(rem, 'restart_service') as mock_restart:
            mock_health.return_value = {'status': 'healthy'}
            
            # WHEN remediation is executed
            exit_code = rem.remediate()
            
            # THEN no restart is performed
            assert exit_code == 0
            mock_restart.assert_not_called()

def test_given_restart_fails_when_remediate_then_exit_code_1(behaviour_args):
    # GIVEN a service that fails to restart
    rem = PasswordResetServiceRemediator(behaviour_args)
    
    with patch.object(rem, 'check_service_health') as mock_health:
        with patch.object(rem, 'restart_service') as mock_restart:
            mock_health.return_value = {'status': 'unhealthy'}
            mock_restart.return_value = False
            
            # WHEN remediation is attempted
            exit_code = rem.remediate()
            
            # THEN exit code indicates restart failure
            assert exit_code == 1

def test_given_backend_integration_fails_when_remediate_then_exit_code_3(behaviour_args):
    # GIVEN a service with backend integration failure
    rem = PasswordResetServiceRemediator(behaviour_args)
    
    with patch.object(rem, 'check_service_health') as mock_health:
        with patch.object(rem, 'restart_service') as mock_restart:
            with patch.object(rem, 'wait_for_service_ready') as mock_wait:
                with patch.object(rem, 'verify_backend_integration') as mock_verify:
                    mock_health.return_value = {'status': 'unhealthy'}
                    mock_restart.return_value = True
                    mock_wait.return_value = True
                    mock_verify.return_value = False
                    
                    # WHEN remediation is executed
                    exit_code = rem.remediate()
                    
                    # THEN exit code indicates integration failure
                    assert exit_code == 3

def test_given_password_reset_flow_fails_when_remediate_then_exit_code_4(behaviour_args):
    # GIVEN a service where password reset flow test fails
    rem = PasswordResetServiceRemediator(behaviour_args)
    
    with patch.object(rem, 'check_service_health') as mock_health:
        with patch.object(rem, 'restart_service') as mock_restart:
            with patch.object(rem, 'wait_for_service_ready') as mock_wait:
                with patch.object(rem, 'verify_backend_integration') as mock_verify:
                    with patch.object(rem, 'test_password_reset_flow') as mock_test:
                        mock_health.return_value = {'status': 'unhealthy'}
                        mock_restart.return_value = True
                        mock_wait.return_value = True
                        mock_verify.return_value = True
                        mock_test.return_value = False
                        
                        # WHEN remediation is executed
                        exit_code = rem.remediate()
                        
                        # THEN exit code indicates flow test failure
                        assert exit_code == 4

def test_given_dry_run_mode_when_remediate_then_no_actual_changes(behaviour_args):
    # GIVEN dry-run mode is enabled
    behaviour_args.dry_run = True
    rem = PasswordResetServiceRemediator(behaviour_args)
    
    with patch.object(rem.session, 'post') as mock_post:
        with patch.object(rem, 'check_service_health') as mock_health:
            mock_health.return_value = {'status': 'unhealthy'}
            
            # WHEN remediation is executed
            exit_code = rem.remediate()
            
            # THEN no actual service changes are made
            assert exit_code == 0
            mock_post.assert_not_called()

def test_given_service_not_ready_when_wait_then_retries_exhausted(behaviour_args):
    # GIVEN a service that never becomes ready
    rem = PasswordResetServiceRemediator(behaviour_args)
    
    with patch.object(rem, 'check_service_health') as mock_health:
        with patch('time.sleep'):
            mock_health.return_value = {'status': 'unhealthy'}
            
            # WHEN waiting for service to be ready
            result = rem.wait_for_service_ready()
            
            # THEN wait times out after max retries
            assert result is False
            assert mock_health.call_count == behaviour_args.max_retries