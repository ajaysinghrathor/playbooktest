#!/usr/bin/env python3
import argparse
import logging
import os
import sys
import pymysql
from typing import Dict, List, Tuple

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MySQLConnectionRemediator:
    def __init__(self, host: str, port: int, user: str, password: str, 
                 idle_threshold: int, max_connections: int, 
                 thread_threshold: int, dry_run: bool):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.idle_threshold = idle_threshold
        self.max_connections = max_connections
        self.thread_threshold = thread_threshold
        self.dry_run = dry_run
        self.conn = None

    def connect(self) -> None:
        try:
            self.conn = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                connect_timeout=10
            )
            logger.info(f"Connected to MySQL at {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to connect to MySQL: {e}")
            raise

    def get_thread_count(self) -> int:
        with self.conn.cursor() as cursor:
            cursor.execute("SHOW STATUS LIKE 'Threads_connected'")
            result = cursor.fetchone()
            count = int(result[1]) if result else 0
            logger.info(f"Current threads connected: {count}")
            return count

    def get_max_connections(self) -> int:
        with self.conn.cursor() as cursor:
            cursor.execute("SHOW VARIABLES LIKE 'max_connections'")
            result = cursor.fetchone()
            max_conn = int(result[1]) if result else 0
            logger.info(f"Current max_connections: {max_conn}")
            return max_conn

    def get_idle_connections(self) -> List[Dict]:
        query = """
            SELECT id, user, host, db, command, time, state, info
            FROM information_schema.processlist
            WHERE command = 'Sleep' AND time > %s AND id != CONNECTION_ID()
            ORDER BY time DESC
        """
        with self.conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(query, (self.idle_threshold,))
            results = cursor.fetchall()
            logger.info(f"Found {len(results)} idle connections exceeding {self.idle_threshold}s")
            return results

    def kill_connection(self, conn_id: int) -> bool:
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(f"KILL {conn_id}")
            logger.info(f"Killed connection ID {conn_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to kill connection {conn_id}: {e}")
            return False

    def set_max_connections(self, value: int) -> bool:
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(f"SET GLOBAL max_connections = {value}")
            logger.info(f"Set max_connections to {value}")
            return True
        except Exception as e:
            logger.error(f"Failed to set max_connections: {e}")
            return False

    def flush_threads(self) -> bool:
        try:
            with self.conn.cursor() as cursor:
                cursor.execute("FLUSH STATUS")
            logger.info("Flushed thread cache")
            return True
        except Exception as e:
            logger.warning(f"Failed to flush threads: {e}")
            return False

    def remediate(self) -> Tuple[bool, Dict]:
        result = {
            'initial_threads': 0,
            'final_threads': 0,
            'killed_connections': 0,
            'max_connections_updated': False,
            'actions': []
        }

        try:
            self.connect()
            initial_threads = self.get_thread_count()
            result['initial_threads'] = initial_threads

            if initial_threads < self.thread_threshold:
                logger.info(f"Thread count {initial_threads} below threshold {self.thread_threshold}, no action needed")
                result['final_threads'] = initial_threads
                return True, result

            logger.warning(f"Thread count {initial_threads} exceeds threshold {self.thread_threshold}")
            result['actions'].append('threshold_exceeded')

            idle_conns = self.get_idle_connections()
            if idle_conns:
                logger.info(f"Terminating {len(idle_conns)} idle connections")
                for conn in idle_conns:
                    if self.dry_run:
                        logger.info(f"[DRY-RUN] Would kill connection {conn['id']} (user={conn['user']}, idle={conn['time']}s)")
                        result['killed_connections'] += 1
                    else:
                        if self.kill_connection(conn['id']):
                            result['killed_connections'] += 1
                result['actions'].append(f'killed_{result["killed_connections"]}_idle')

            current_max = self.get_max_connections()
            if current_max < self.max_connections:
                logger.info(f"Increasing max_connections from {current_max} to {self.max_connections}")
                if self.dry_run:
                    logger.info(f"[DRY-RUN] Would set max_connections to {self.max_connections}")
                    result['max_connections_updated'] = True
                else:
                    result['max_connections_updated'] = self.set_max_connections(self.max_connections)
                if result['max_connections_updated']:
                    result['actions'].append('max_connections_increased')

            if not self.dry_run:
                self.flush_threads()
                result['actions'].append('thread_cache_flushed')

            final_threads = self.get_thread_count()
            result['final_threads'] = final_threads

            if final_threads < self.thread_threshold:
                logger.info(f"Remediation successful: threads reduced from {initial_threads} to {final_threads}")
                return True, result
            else:
                logger.warning(f"Threads still at {final_threads} after remediation, may need additional intervention")
                return True, result

        except Exception as e:
            logger.error(f"Remediation failed: {e}")
            return False, result
        finally:
            if self.conn:
                self.conn.close()
                logger.info("MySQL connection closed")


def main():
    parser = argparse.ArgumentParser(
        description='Remediate MySQL thread connection threshold breach'
    )
    parser.add_argument('--host', required=True,
                        default=os.getenv('MYSQL_HOST'),
                        help='MySQL host address')
    parser.add_argument('--port', type=int,
                        default=os.getenv('MYSQL_PORT', 3306),
                        help='MySQL port (default: 3306)')
    parser.add_argument('--user', required=True,
                        default=os.getenv('MYSQL_USER'),
                        help='MySQL username')
    parser.add_argument('--password', required=True,
                        default=os.getenv('MYSQL_PASSWORD'),
                        help='MySQL password')
    parser.add_argument('--idle-threshold', type=int,
                        default=os.getenv('MYSQL_IDLE_THRESHOLD', 300),
                        help='Idle time threshold in seconds to kill connections (default: 300)')
    parser.add_argument('--max-connections', type=int,
                        default=os.getenv('MYSQL_MAX_CONNECTIONS', 1000),
                        help='Target max_connections value (default: 1000)')
    parser.add_argument('--thread-threshold', type=int,
                        default=os.getenv('MYSQL_THREAD_THRESHOLD', 551),
                        help='Thread count threshold to trigger remediation (default: 551)')
    parser.add_argument('--dry-run', action='store_true',
                        default=os.getenv('MYSQL_DRY_RUN', '').lower() == 'true',
                        help='Execute in dry-run mode without making changes')

    args = parser.parse_args()

    if args.dry_run:
        logger.info("=== DRY-RUN MODE ENABLED ===")

    remediator = MySQLConnectionRemediator(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        idle_threshold=args.idle_threshold,
        max_connections=args.max_connections,
        thread_threshold=args.thread_threshold,
        dry_run=args.dry_run
    )

    success, result = remediator.remediate()

    logger.info(f"Remediation summary: {result}")

    if success:
        logger.info("Remediation completed successfully")
        sys.exit(0)
    else:
        logger.error("Remediation failed")
        sys.exit(1)


if __name__ == '__main__':
    main()