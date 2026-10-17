#!/usr/bin/env python3
import sys
import logging
import argparse
import pymysql
from typing import List, Dict

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MySQLConnectionRemediator:
    def __init__(self, host: str, port: int, user: str, password: str,
                 idle_timeout: int, long_query_time: int, max_kills: int):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.idle_timeout = idle_timeout
        self.long_query_time = long_query_time
        self.max_kills = max_kills
        self.connection = None

    def connect(self):
        try:
            self.connection = pymysql.connect(
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
        cursor = self.connection.cursor()
        cursor.execute("SHOW STATUS LIKE 'Threads_connected'")
        result = cursor.fetchone()
        cursor.close()
        count = int(result[1]) if result else 0
        logger.info(f"Current thread count: {count}")
        return count

    def get_idle_connections(self) -> List[Dict]:
        cursor = self.connection.cursor(pymysql.cursors.DictCursor)
        query = f"""
            SELECT id, user, host, db, command, time, state
            FROM information_schema.processlist
            WHERE command = 'Sleep'
            AND time > {self.idle_timeout}
            AND id != CONNECTION_ID()
            ORDER BY time DESC
        """
        cursor.execute(query)
        results = cursor.fetchall()
        cursor.close()
        logger.info(f"Found {len(results)} idle connections exceeding {self.idle_timeout}s")
        return results

    def get_long_running_queries(self) -> List[Dict]:
        cursor = self.connection.cursor(pymysql.cursors.DictCursor)
        query = f"""
            SELECT id, user, host, db, command, time, state, LEFT(info, 100) as query_preview
            FROM information_schema.processlist
            WHERE command != 'Sleep'
            AND time > {self.long_query_time}
            AND id != CONNECTION_ID()
            AND user != 'system user'
            ORDER BY time DESC
        """
        cursor.execute(query)
        results = cursor.fetchall()
        cursor.close()
        logger.info(f"Found {len(results)} long-running queries exceeding {self.long_query_time}s")
        return results

    def kill_connection(self, conn_id: int) -> bool:
        try:
            cursor = self.connection.cursor()
            cursor.execute(f"KILL {conn_id}")
            cursor.close()
            logger.info(f"Killed connection {conn_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to kill connection {conn_id}: {e}")
            return False

    def remediate(self) -> int:
        initial_count = self.get_thread_count()
        killed_count = 0

        idle_connections = self.get_idle_connections()
        for conn in idle_connections[:self.max_kills - killed_count]:
            if self.kill_connection(conn['id']):
                killed_count += 1
                logger.info(f"Killed idle connection: user={conn['user']}, host={conn['host']}, idle_time={conn['time']}s")

        if killed_count < self.max_kills:
            long_queries = self.get_long_running_queries()
            for query in long_queries[:self.max_kills - killed_count]:
                if self.kill_connection(query['id']):
                    killed_count += 1
                    logger.info(f"Killed long query: user={query['user']}, host={query['host']}, runtime={query['time']}s")

        final_count = self.get_thread_count()
        logger.info(f"Remediation complete: killed {killed_count} connections, threads reduced from {initial_count} to {final_count}")
        return killed_count

    def close(self):
        if self.connection:
            self.connection.close()
            logger.info("MySQL connection closed")


def main():
    parser = argparse.ArgumentParser(description='MySQL connection remediation')
    parser.add_argument('--host', required=True, help='MySQL host')
    parser.add_argument('--port', type=int, default=3306, help='MySQL port')
    parser.add_argument('--user', required=True, help='MySQL user')
    parser.add_argument('--password', required=True, help='MySQL password')
    parser.add_argument('--idle-timeout', type=int, default=300, help='Idle timeout in seconds')
    parser.add_argument('--long-query-time', type=int, default=60, help='Long query time in seconds')
    parser.add_argument('--max-kills', type=int, default=50, help='Max connections to kill')

    args = parser.parse_args()

    remediator = MySQLConnectionRemediator(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        idle_timeout=args.idle_timeout,
        long_query_time=args.long_query_time,
        max_kills=args.max_kills
    )

    try:
        remediator.connect()
        killed = remediator.remediate()
        remediator.close()
        if killed > 0:
            logger.info(f"SUCCESS: Remediated {killed} connections")
            sys.exit(0)
        else:
            logger.info("INFO: No connections needed remediation")
            sys.exit(2)
    except Exception as e:
        logger.error(f"FAILED: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()