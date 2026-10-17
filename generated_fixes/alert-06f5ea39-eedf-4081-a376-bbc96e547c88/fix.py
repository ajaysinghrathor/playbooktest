#!/usr/bin/env python3
import sys
import logging
import argparse
import time
from typing import List, Dict, Tuple

try:
    import pymysql
    import pymysql.cursors
except ImportError:
    print("ERROR: pymysql not installed. Install with: pip install pymysql", file=sys.stderr)
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MySQLConnectionRemediator:
    def __init__(self, host: str, port: int, user: str, password: str, threshold: int, max_idle_time: int):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.threshold = threshold
        self.max_idle_time = max_idle_time
        self.connection = None

    def connect(self) -> None:
        try:
            self.connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=10
            )
            logger.info(f"Connected to MySQL at {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to connect to MySQL: {e}")
            raise

    def get_thread_count(self) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute("SHOW STATUS LIKE 'Threads_connected'")
            result = cursor.fetchone()
            count = int(result['Value'])
            logger.info(f"Current thread count: {count}")
            return count

    def get_idle_connections(self) -> List[Dict]:
        with self.connection.cursor() as cursor:
            query = """
                SELECT id, user, host, db, command, time, state, info
                FROM information_schema.processlist
                WHERE command = 'Sleep'
                AND time > %s
                AND id != CONNECTION_ID()
                ORDER BY time DESC
            """
            cursor.execute(query, (self.max_idle_time,))
            idle_conns = cursor.fetchall()
            logger.info(f"Found {len(idle_conns)} idle connections exceeding {self.max_idle_time}s")
            return idle_conns

    def kill_connection(self, conn_id: int) -> bool:
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(f"KILL {conn_id}")
                logger.info(f"Killed connection ID {conn_id}")
                return True
        except Exception as e:
            logger.warning(f"Failed to kill connection {conn_id}: {e}")
            return False

    def remediate(self) -> Tuple[int, int]:
        initial_count = self.get_thread_count()
        
        if initial_count <= self.threshold:
            logger.info(f"Thread count {initial_count} is within threshold {self.threshold}, no action needed")
            return initial_count, 0

        logger.warning(f"Thread count {initial_count} exceeds threshold {self.threshold}, starting remediation")
        
        idle_connections = self.get_idle_connections()
        killed_count = 0
        
        for conn in idle_connections:
            if self.kill_connection(conn['id']):
                killed_count += 1
            time.sleep(0.1)
            
            current_count = self.get_thread_count()
            if current_count <= self.threshold:
                logger.info(f"Thread count reduced to {current_count}, threshold met")
                break
        
        final_count = self.get_thread_count()
        logger.info(f"Remediation complete: killed {killed_count} connections, thread count: {initial_count} -> {final_count}")
        
        return final_count, killed_count

    def close(self) -> None:
        if self.connection:
            self.connection.close()
            logger.info("MySQL connection closed")


def main():
    parser = argparse.ArgumentParser(description='Remediate MySQL high thread connections')
    parser.add_argument('--host', required=True, help='MySQL host')
    parser.add_argument('--port', type=int, default=3306, help='MySQL port')
    parser.add_argument('--user', required=True, help='MySQL user')
    parser.add_argument('--password', required=True, help='MySQL password')
    parser.add_argument('--threshold', type=int, default=551, help='Thread count threshold')
    parser.add_argument('--max-idle-time', type=int, default=300, help='Max idle time in seconds')
    
    args = parser.parse_args()
    
    remediator = None
    try:
        remediator = MySQLConnectionRemediator(
            host=args.host,
            port=args.port,
            user=args.user,
            password=args.password,
            threshold=args.threshold,
            max_idle_time=args.max_idle_time
        )
        
        remediator.connect()
        final_count, killed = remediator.remediate()
        
        if final_count > args.threshold:
            logger.error(f"Thread count {final_count} still exceeds threshold {args.threshold} after remediation")
            sys.exit(1)
        
        logger.info(f"SUCCESS: Remediation completed, killed {killed} connections")
        sys.exit(0)
        
    except Exception as e:
        logger.error(f"Remediation failed: {e}")
        sys.exit(1)
    finally:
        if remediator:
            remediator.close()


if __name__ == '__main__':
    main()