#!/usr/bin/env python3
import sys
import logging
import argparse
import time
from typing import Dict, List, Tuple

try:
    import pymysql
except ImportError:
    print("ERROR: pymysql library not found. Install with: pip install pymysql", file=sys.stderr)
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

IDLE_TIMEOUT_SECONDS = 300
MAX_QUERY_TIME_SECONDS = 600
THREAD_THRESHOLD = 551
TARGET_THREAD_COUNT = 400


class MySQLConnectionRemediator:
    def __init__(self, host: str, port: int, user: str, password: str):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
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

    def close(self) -> None:
        if self.connection:
            self.connection.close()
            logger.info("MySQL connection closed")

    def get_thread_count(self) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute("SHOW STATUS LIKE 'Threads_connected'")
            result = cursor.fetchone()
            return int(result[1]) if result else 0

    def get_processlist(self) -> List[Dict]:
        with self.connection.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SHOW FULL PROCESSLIST")
            return cursor.fetchall()

    def kill_connection(self, thread_id: int) -> bool:
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(f"KILL {thread_id}")
                self.connection.commit()
                return True
        except Exception as e:
            logger.warning(f"Failed to kill thread {thread_id}: {e}")
            return False

    def identify_idle_connections(self, processes: List[Dict]) -> List[int]:
        idle_threads = []
        for proc in processes:
            if proc['Command'] == 'Sleep' and proc['Time'] and int(proc['Time']) > IDLE_TIMEOUT_SECONDS:
                if proc['User'] not in ('root', 'system user', 'event_scheduler'):
                    idle_threads.append(proc['Id'])
        return idle_threads

    def identify_long_queries(self, processes: List[Dict]) -> List[int]:
        long_queries = []
        for proc in processes:
            if proc['Command'] == 'Query' and proc['Time'] and int(proc['Time']) > MAX_QUERY_TIME_SECONDS:
                if proc['User'] not in ('root', 'system user'):
                    long_queries.append(proc['Id'])
        return long_queries

    def remediate(self) -> Tuple[int, int, int]:
        initial_count = self.get_thread_count()
        logger.info(f"Initial thread count: {initial_count}")

        if initial_count < THREAD_THRESHOLD:
            logger.info(f"Thread count {initial_count} is below threshold {THREAD_THRESHOLD}, no action needed")
            return initial_count, 0, initial_count

        processes = self.get_processlist()
        logger.info(f"Retrieved {len(processes)} active processes")

        idle_threads = self.identify_idle_connections(processes)
        logger.info(f"Found {len(idle_threads)} idle connections exceeding {IDLE_TIMEOUT_SECONDS}s")

        long_queries = self.identify_long_queries(processes)
        logger.info(f"Found {len(long_queries)} long-running queries exceeding {MAX_QUERY_TIME_SECONDS}s")

        killed_count = 0
        threads_to_kill = set(idle_threads + long_queries)

        for thread_id in threads_to_kill:
            current_count = self.get_thread_count()
            if current_count <= TARGET_THREAD_COUNT:
                logger.info(f"Target thread count {TARGET_THREAD_COUNT} reached, stopping remediation")
                break

            if self.kill_connection(thread_id):
                killed_count += 1
                logger.info(f"Killed thread {thread_id} ({killed_count}/{len(threads_to_kill)})")
                time.sleep(0.1)

        time.sleep(1)
        final_count = self.get_thread_count()
        logger.info(f"Remediation complete: killed {killed_count} threads, final count: {final_count}")

        return initial_count, killed_count, final_count


def main():
    parser = argparse.ArgumentParser(description='Remediate MySQL high thread connections')
    parser.add_argument('--host', required=True, help='MySQL host')
    parser.add_argument('--port', type=int, default=3306, help='MySQL port')
    parser.add_argument('--user', required=True, help='MySQL user')
    parser.add_argument('--password', required=True, help='MySQL password')
    args = parser.parse_args()

    remediator = MySQLConnectionRemediator(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password
    )

    try:
        remediator.connect()
        initial, killed, final = remediator.remediate()

        logger.info(f"Summary: Initial={initial}, Killed={killed}, Final={final}")

        if final < THREAD_THRESHOLD:
            logger.info("SUCCESS: Thread count reduced below threshold")
            return 0
        else:
            logger.warning(f"Thread count {final} still above threshold {THREAD_THRESHOLD}")
            return 1

    except Exception as e:
        logger.error(f"Remediation failed: {e}")
        return 1
    finally:
        remediator.close()


if __name__ == '__main__':
    sys.exit(main())