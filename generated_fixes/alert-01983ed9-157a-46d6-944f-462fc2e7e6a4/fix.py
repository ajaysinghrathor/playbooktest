#!/usr/bin/env python3
import argparse
import logging
import os
import sys
import time
import requests
from typing import Dict, Any

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class PasswordResetServiceRemediator:
    def __init__(self, args):
        self.service_endpoint = args.service_endpoint
        self.service_name = args.service_name
        self.business_service = args.business_service
        self.region = args.region
        self.api_key = args.api_key
        self.timeout = args.timeout
        self.max_retries = args.max_retries
        self.dry_run = args.dry_run
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update({'Authorization': f'Bearer {self.api_key}'})

    def check_service_health(self) -> Dict[str, Any]:
        logger.info(f"Checking health of password reset service: {self.service_endpoint}")
        try:
            response = self.session.get(
                f"{self.service_endpoint}/health",
                timeout=self.timeout
            )
            response.raise_for_status()
            health_data = response.json()
            logger.info(f"Health check response: {health_data}")
            return health_data
        except requests.exceptions.RequestException as e:
            logger.error(f"Health check failed: {e}")
            return {"status": "unhealthy", "error": str(e)}

    def restart_service(self) -> bool:
        logger.info(f"Restarting password reset service: {self.service_name}")
        if self.dry_run:
            logger.info("[DRY-RUN] Would restart service")
            return True
        
        try:
            response = self.session.post(
                f"{self.service_endpoint}/admin/restart",
                json={
                    "service_name": self.service_name,
                    "business_service": self.business_service,
                    "region": self.region
                },
                timeout=self.timeout
            )
            response.raise_for_status()
            logger.info("Service restart initiated successfully")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Service restart failed: {e}")
            return False

    def verify_backend_integration(self) -> bool:
        logger.info("Verifying backend authentication integration")
        try:
            response = self.session.get(
                f"{self.service_endpoint}/admin/integrations/check",
                params={
                    "business_service": self.business_service,
                    "region": self.region
                },
                timeout=self.timeout
            )
            response.raise_for_status()
            integration_status = response.json()
            logger.info(f"Integration status: {integration_status}")
            return integration_status.get("status") == "healthy"
        except requests.exceptions.RequestException as e:
            logger.error(f"Backend integration check failed: {e}")
            return False

    def test_password_reset_flow(self) -> bool:
        logger.info("Testing password reset flow with synthetic request")
        if self.dry_run:
            logger.info("[DRY-RUN] Would test password reset flow")
            return True
        
        try:
            response = self.session.post(
                f"{self.service_endpoint}/test/reset",
                json={
                    "test_user": "synthetic_test_user",
                    "business_service": self.business_service,
                    "region": self.region
                },
                timeout=self.timeout
            )
            response.raise_for_status()
            result = response.json()
            success = result.get("test_passed", False)
            logger.info(f"Password reset flow test: {'PASSED' if success else 'FAILED'}")
            return success
        except requests.exceptions.RequestException as e:
            logger.error(f"Password reset flow test failed: {e}")
            return False

    def wait_for_service_ready(self) -> bool:
        logger.info("Waiting for service to become ready")
        for attempt in range(self.max_retries):
            if self.dry_run:
                logger.info(f"[DRY-RUN] Would check service ready (attempt {attempt + 1}/{self.max_retries})")
                return True
            
            time.sleep(5)
            health = self.check_service_health()
            if health.get("status") == "healthy":
                logger.info("Service is ready")
                return True
            logger.warning(f"Service not ready yet (attempt {attempt + 1}/{self.max_retries})")
        
        logger.error("Service did not become ready within retry limit")
        return False

    def remediate(self) -> int:
        logger.info("=" * 60)
        logger.info("Starting AH Password Reset Service Remediation")
        logger.info(f"Business Service: {self.business_service}")
        logger.info(f"Region: {self.region}")
        logger.info(f"Dry Run: {self.dry_run}")
        logger.info("=" * 60)

        initial_health = self.check_service_health()
        if initial_health.get("status") == "healthy" and not self.dry_run:
            logger.info("Service is already healthy, no remediation needed")
            return 0

        if not self.restart_service():
            logger.error("Failed to restart service")
            return 1

        if not self.wait_for_service_ready():
            logger.error("Service did not recover after restart")
            return 2

        if not self.verify_backend_integration():
            logger.error("Backend integration check failed")
            return 3

        if not self.test_password_reset_flow():
            logger.error("Password reset flow test failed")
            return 4

        logger.info("=" * 60)
        logger.info("Remediation completed successfully")
        logger.info("=" * 60)
        return 0

def parse_args():
    parser = argparse.ArgumentParser(
        description='Remediate AH password reset service failures'
    )
    parser.add_argument(
        '--service-endpoint',
        required=True,
        default=os.getenv('SERVICE_ENDPOINT'),
        help='Password reset service API endpoint URL'
    )
    parser.add_argument(
        '--service-name',
        required=True,
        default=os.getenv('SERVICE_NAME'),
        help='Name of the password reset service'
    )
    parser.add_argument(
        '--business-service',
        required=True,
        default=os.getenv('BUSINESS_SERVICE'),
        help='Business service identifier (e.g., AH1432AP305-01)'
    )
    parser.add_argument(
        '--region',
        required=True,
        default=os.getenv('REGION'),
        help='Region code (e.g., NL)'
    )
    parser.add_argument(
        '--api-key',
        default=os.getenv('API_KEY'),
        help='API authentication key for service endpoints'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=int(os.getenv('TIMEOUT', '60')),
        help='HTTP request timeout in seconds (default: 60)'
    )
    parser.add_argument(
        '--max-retries',
        type=int,
        default=int(os.getenv('MAX_RETRIES', '3')),
        help='Maximum retry attempts for service health checks (default: 3)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=os.getenv('DRY_RUN', '').lower() in ('true', '1', 'yes'),
        help='Run in dry-run mode without making changes'
    )
    return parser.parse_args()

def main():
    args = parse_args()
    remediator = PasswordResetServiceRemediator(args)
    try:
        exit_code = remediator.remediate()
        sys.exit(exit_code)
    except Exception as e:
        logger.exception(f"Unexpected error during remediation: {e}")
        sys.exit(99)

if __name__ == '__main__':
    main()