#!/usr/bin/env python3
import argparse
import logging
import sys
import pymysql
from typing import List, Dict

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MySQLConnectionRemediator:
    def __init__(self, host: str, port: int, user: str, password: str, 
                 idle_threshold: int = 300, max_kill: int = 100):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.idle_threshold = idle_threshold
        self.max_kill = max_kill
        self.connection = None

    def connect(self):
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
        cursor = self.connection.cursor()
        cursor.execute("SHOW STATUS LIKE 'Threads_connected'")
        result = cursor.fetchone()
        cursor.close()
        if result:
            count = int(result[1])
            logger.info(f"Current THREADS_CONNECTED: {count}")
            return count
        return 0

    def get_idle_connections(self) -> List[Dict]:
        cursor = self.connection.cursor(pymysql.cursors.DictCursor)
        query = """
            SELECT ID, USER, HOST, DB, COMMAND, TIME, STATE, INFO
            FROM information_schema.PROCESSLIST
            WHERE COMMAND = 'Sleep'
            AND TIME > %s
            AND ID != CONNECTION_ID()
            ORDER BY TIME DESC
            LIMIT %s
        """
        cursor.execute(query, (self.idle_threshold, self.max_kill))
        results = cursor.fetchall()
        cursor.close()
        logger.info(f"Found {len(results)} idle connections exceeding {self.idle_threshold}s")
        return results

    def kill_connection(self, connection_id: int) -> bool:
        try:
            cursor = self.connection.cursor()
            cursor.execute(f"KILL {connection_id}")
            cursor.close()
            logger.info(f"Killed connection ID: {connection_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to kill connection {connection_id}: {e}")
            return False

    def remediate(self) -> int:
        initial_count = self.get_thread_count()
        logger.info(f"Starting remediation. Initial thread count: {initial_count}")
        
        idle_connections = self.get_idle_connections()
        if not idle_connections:
            logger.info("No idle connections found to kill")
            return 0

        killed_count = 0
        for conn in idle_connections:
            if self.kill_connection(conn['ID']):
                killed_count += 1

        final_count = self.get_thread_count()
        logger.info(f"Remediation complete. Killed {killed_count} connections. "
                   f"Thread count: {initial_count} -> {final_count}")
        return killed_count

    def close(self):
        if self.connection:
            self.connection.close()
            logger.info("MySQL connection closed")


def main():
    parser = argparse.ArgumentParser(description='Remediate MySQL high thread connections')
    parser.add_argument('--host', required=True, help='MySQL host')
    parser.add_argument('--port', type=int, default=3306, help='MySQL port')
    parser.add_argument('--user', required=True, help='MySQL user')
    parser.add_argument('--password', required=True, help='MySQL password')
    parser.add_argument('--idle-threshold', type=int, default=300, 
                       help='Idle time threshold in seconds')
    parser.add_argument('--max-kill', type=int, default=100,
                       help='Maximum connections to kill')
    
    args = parser.parse_args()

    remediator = MySQLConnectionRemediator(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        idle_threshold=args.idle_threshold,
        max_kill=args.max_kill
    )

    try:
        remediator.connect()
        killed = remediator.remediate()
        remediator.close()
        
        if killed > 0:
            logger.info(f"SUCCESS: Remediation completed, killed {killed} idle connections")
            sys.exit(0)
        else:
            logger.info("SUCCESS: No remediation needed")
            sys.exit(0)
    except Exception as e:
        logger.error(f"FAILED: Remediation error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()