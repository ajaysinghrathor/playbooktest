#!/usr/bin/env python3
import sys
import logging
import argparse
import time
from typing import List, Dict, Any

try:
    import pymysql
except ImportError:
    print("ERROR: pymysql module required. Install via: pip install pymysql", file=sys.stderr)
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


class MySQLConnectionRemediator:
    def __init__(self, host: str, port: int, user: str, password: str,
                 idle_threshold: int, max_threshold: int):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.idle_threshold = idle_threshold
        self.max_threshold = max_threshold
        self.connection = None

    def connect(self) -> None:
        try:
            self.connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                connect_timeout=10,
                read_timeout=30
            )
            logger.info(f"Connected to MySQL at {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to connect to MySQL: {e}")
            raise

    def get_thread_count(self) -> int:
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SHOW STATUS LIKE 'Threads_connected'")
                result = cursor.fetchone()
                if result:
                    count = int(result[1])
                    logger.info(f"Current thread count: {count}")
                    return count
                return 0
        except Exception as e:
            logger.error(f"Failed to get thread count: {e}")
            raise

    def get_idle_connections(self) -> List[Dict[str, Any]]:
        try:
            with self.connection.cursor(pymysql.cursors.DictCursor) as cursor:
                query = f"""
                SELECT ID, USER, HOST, DB, COMMAND, TIME, STATE, INFO
                FROM information_schema.PROCESSLIST
                WHERE COMMAND = 'Sleep'
                AND TIME > {self.idle_threshold}
                AND ID != CONNECTION_ID()
                ORDER BY TIME DESC
                """
                cursor.execute(query)
                results = cursor.fetchall()
                logger.info(f"Found {len(results)} idle connections exceeding {self.idle_threshold}s")
                return results
        except Exception as e:
            logger.error(f"Failed to query idle connections: {e}")
            raise

    def kill_connection(self, conn_id: int) -> bool:
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(f"KILL {conn_id}")
                logger.info(f"Killed connection ID {conn_id}")
                return True
        except Exception as e:
            logger.warning(f"Failed to kill connection {conn_id}: {e}")
            return False

    def remediate(self) -> int:
        logger.info("Starting MySQL connection remediation")
        
        initial_count = self.get_thread_count()
        if initial_count <= self.max_threshold:
            logger.info(f"Thread count {initial_count} is within threshold {self.max_threshold}, no action needed")
            return 0

        idle_conns = self.get_idle_connections()
        if not idle_conns:
            logger.warning("No idle connections found to terminate")
            return 1

        killed = 0
        for conn in idle_conns:
            if self.kill_connection(conn['ID']):
                killed += 1
            time.sleep(0.1)

        logger.info(f"Terminated {killed} idle connections")
        
        time.sleep(2)
        final_count = self.get_thread_count()
        
        if final_count > self.max_threshold:
            logger.error(f"Thread count still {final_count} after cleanup (threshold: {self.max_threshold})")
            return 1
        
        logger.info(f"Remediation successful: {initial_count} -> {final_count} threads")
        return 0

    def close(self) -> None:
        if self.connection:
            self.connection.close()
            logger.info("MySQL connection closed")


def main():
    parser = argparse.ArgumentParser(description='MySQL connection thread remediation')
    parser.add_argument('--host', required=True, help='MySQL host')
    parser.add_argument('--port', type=int, default=3306, help='MySQL port')
    parser.add_argument('--user', required=True, help='MySQL user')
    parser.add_argument('--password', required=True, help='MySQL password')
    parser.add_argument('--idle-threshold', type=int, default=300, help='Idle seconds threshold')
    parser.add_argument('--max-threshold', type=int, default=551, help='Max connections threshold')
    
    args = parser.parse_args()
    
    remediator = MySQLConnectionRemediator(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        idle_threshold=args.idle_threshold,
        max_threshold=args.max_threshold
    )
    
    try:
        remediator.connect()
        exit_code = remediator.remediate()
        remediator.close()
        sys.exit(exit_code)
    except Exception as e:
        logger.error(f"Remediation failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()