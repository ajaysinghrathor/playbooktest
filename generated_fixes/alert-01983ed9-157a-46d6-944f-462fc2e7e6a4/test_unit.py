#!/usr/bin/env python3
import pytest
from unittest.mock import Mock, patch, MagicMock
from argparse import Namespace
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from fix import PasswordResetServiceRemediator

@pytest.fixture
def mock_args():
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

@pytest.fixture
def remediator(mock_args):
    return PasswordResetServiceRemediator(mock_args)

def test_init_sets_attributes(mock_args):
    rem = PasswordResetServiceRemediator(mock_args)
    assert rem.service_endpoint == 'https://test.example.com/api'
    assert rem.service_name == 'test-service'
    assert rem.business_service == 'AH1432AP305-01'
    assert rem.region == 'NL'
    assert rem.api_key == 'test-key'

def test_check_service_health_success(remediator):
    with patch.object(remediator.session, 'get') as mock_get:
        mock_response = Mock()
        mock_response.json.return_value = {'status': 'healthy'}
        mock_get.return_value = mock_response
        
        result = remediator.check_service_health()
        
        assert result['status'] == 'healthy'
        mock_get.assert_called_once()

def test_check_service_health_failure(remediator):
    with patch.object(remediator.session, 'get') as mock_get:
        mock_get.side_effect = Exception('Connection failed')
        
        result = remediator.check_service_health()
        
        assert result['status'] == 'unhealthy'
        assert 'error' in result

def test_restart_service_success(remediator):
    with patch.object(remediator.session, 'post') as mock_post:
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        result = remediator.restart_service()
        
        assert result is True
        mock_post.assert_called_once()

def test_restart_service_dry_run(mock_args):
    mock_args.dry_run = True
    rem = PasswordResetServiceRemediator(mock_args)
    
    with patch.object(rem.session, 'post') as mock_post:
        result = rem.restart_service()
        
        assert result is True
        mock_post.assert_not_called()

def test_restart_service_failure(remediator):
    with patch.object(remediator.session, 'post') as mock_post:
        mock_post.side_effect = Exception('Restart failed')
        
        result = remediator.restart_service()
        
        assert result is False

def test_verify_backend_integration_success(remediator):
    with patch.object(remediator.session, 'get') as mock_get:
        mock_response = Mock()
        mock_response.json.return_value = {'status': 'healthy'}
        mock_get.return_value = mock_response
        
        result = remediator.verify_backend_integration()
        
        assert result is True

def test_verify_backend_integration_failure(remediator):
    with patch.object(remediator.session, 'get') as mock_get:
        mock_response = Mock()
        mock_response.json.return_value = {'status': 'unhealthy'}
        mock_get.return_value = mock_response
        
        result = remediator.verify_backend_integration()
        
        assert result is False

def test_test_password_reset_flow_success(remediator):
    with patch.object(remediator.session, 'post') as mock_post:
        mock_response = Mock()
        mock_response.json.return_value = {'test_passed': True}
        mock_post.return_value = mock_response
        
        result = remediator.test_password_reset_flow()
        
        assert result is True

def test_test_password_reset_flow_dry_run(mock_args):
    mock_args.dry_run = True
    rem = PasswordResetServiceRemediator(mock_args)
    
    result = rem.test_password_reset_flow()
    
    assert result is True

def test_wait_for_service_ready_success(remediator):
    with patch.object(remediator, 'check_service_health') as mock_health:
        mock_health.return_value = {'status': 'healthy'}
        
        result = remediator.wait_for_service_ready()
        
        assert result is True

def test_wait_for_service_ready_timeout(remediator):
    with patch.object(remediator, 'check_service_health') as mock_health:
        with patch('time.sleep'):
            mock_health.return_value = {'status': 'unhealthy'}
            
            result = remediator.wait_for_service_ready()
            
            assert result is False

def test_remediate_already_healthy(remediator):
    with patch.object(remediator, 'check_service_health') as mock_health:
        mock_health.return_value = {'status': 'healthy'}
        
        result = remediator.remediate()
        
        assert result == 0

def test_remediate_restart_fails(remediator):
    with patch.object(remediator, 'check_service_health') as mock_health:
        with patch.object(remediator, 'restart_service') as mock_restart:
            mock_health.return_value = {'status': 'unhealthy'}
            mock_restart.return_value = False
            
            result = remediator.remediate()
            
            assert result == 1

def test_remediate_success(remediator):
    with patch.object(remediator, 'check_service_health') as mock_health:
        with patch.object(remediator, 'restart_service') as mock_restart:
            with patch.object(remediator, 'wait_for_service_ready') as mock_wait:
                with patch.object(remediator, 'verify_backend_integration') as mock_verify:
                    with patch.object(remediator, 'test_password_reset_flow') as mock_test:
                        mock_health.return_value = {'status': 'unhealthy'}
                        mock_restart.return_value = True
                        mock_wait.return_value = True
                        mock_verify.return_value = True
                        mock_test.return_value = True
                        
                        result = remediator.remediate()
                        
                        assert result == 0