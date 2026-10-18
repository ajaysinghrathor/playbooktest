#!/usr/bin/env python3
import argparse
import logging
import sys
import pymysql
from typing import List, Dict

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

THREAD_THRESHOLD = 551
SAFE_THRESHOLD = 400
IDLE_TIME_SECONDS = 300


class MySQLThreadRemediator:
    def __init__(self, host: str, port: int, user: str, password: str):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.connection = None

    def connect(self) -> bool:
        try:
            self.connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                connect_timeout=10,
                cursorclass=pymysql.cursors.DictCursor
            )
            logger.info(f"Connected to MySQL at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to MySQL: {e}")
            return False

    def get_thread_count(self) -> int:
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SHOW STATUS LIKE 'Threads_connected'")
                result = cursor.fetchone()
                count = int(result['Value'])
                logger.info(f"Current THREADS_CONNECTED: {count}")
                return count
        except Exception as e:
            logger.error(f"Failed to get thread count: {e}")
            raise

    def get_idle_connections(self) -> List[Dict]:
        try:
            with self.connection.cursor() as cursor:
                query = f"""
                SELECT id, user, host, db, command, time, state
                FROM information_schema.processlist
                WHERE command = 'Sleep'
                AND time > {IDLE_TIME_SECONDS}
                AND id != CONNECTION_ID()
                ORDER BY time DESC
                """
                cursor.execute(query)
                results = cursor.fetchall()
                logger.info(f"Found {len(results)} idle connections (>5min)")
                return results
        except Exception as e:
            logger.error(f"Failed to get idle connections: {e}")
            raise

    def kill_connection(self, conn_id: int) -> bool:
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(f"KILL {conn_id}")
                logger.info(f"Killed connection ID: {conn_id}")
                return True
        except Exception as e:
            logger.warning(f"Failed to kill connection {conn_id}: {e}")
            return False

    def remediate(self) -> bool:
        try:
            current_threads = self.get_thread_count()
            
            if current_threads <= THREAD_THRESHOLD:
                logger.info(f"Thread count {current_threads} is below threshold {THREAD_THRESHOLD}, no action needed")
                return True

            logger.warning(f"Thread count {current_threads} exceeds threshold {THREAD_THRESHOLD}, starting remediation")
            
            idle_connections = self.get_idle_connections()
            
            if not idle_connections:
                logger.warning("No idle connections to kill, manual investigation required")
                return False

            killed_count = 0
            for conn in idle_connections:
                if self.kill_connection(conn['id']):
                    killed_count += 1
                
                current_threads = self.get_thread_count()
                if current_threads <= SAFE_THRESHOLD:
                    logger.info(f"Reached safe threshold {SAFE_THRESHOLD}, stopped cleanup")
                    break

            logger.info(f"Killed {killed_count} idle connections")
            
            final_threads = self.get_thread_count()
            
            if final_threads <= SAFE_THRESHOLD:
                logger.info(f"Remediation successful: threads reduced to {final_threads}")
                return True
            else:
                logger.warning(f"Thread count {final_threads} still above safe threshold {SAFE_THRESHOLD}")
                return False

        except Exception as e:
            logger.error(f"Remediation failed: {e}")
            return False

    def close(self):
        if self.connection:
            self.connection.close()
            logger.info("Closed MySQL connection")


def main():
    parser = argparse.ArgumentParser(description='MySQL Thread Connection Remediation')
    parser.add_argument('--host', required=True, help='MySQL host')
    parser.add_argument('--port', type=int, default=3306, help='MySQL port')
    parser.add_argument('--user', required=True, help='MySQL user')
    parser.add_argument('--password', default='', help='MySQL password')
    
    args = parser.parse_args()
    
    remediator = MySQLThreadRemediator(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password
    )
    
    try:
        if not remediator.connect():
            sys.exit(1)
        
        if remediator.remediate():
            logger.info("Remediation completed successfully")
            sys.exit(0)
        else:
            logger.error("Remediation completed with warnings")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)
    finally:
        remediator.close()


if __name__ == '__main__':
    main()