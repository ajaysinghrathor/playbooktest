#!/usr/bin/env python3
import sys
import argparse
import logging
import time
from typing import List, Tuple

try:
    import pymysql
    import pymysql.cursors
except ImportError:
    print("ERROR: pymysql module not found. Install with: pip install pymysql", file=sys.stderr)
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

IDLE_THRESHOLD_SECONDS = 300
MAX_QUERY_TIME_SECONDS = 600
TARGET_THREAD_REDUCTION = 100
RESERVED_CONNECTION_BUFFER = 50


def parse_args():
    parser = argparse.ArgumentParser(description='Remediate MySQL thread connection overload')
    parser.add_argument('--host', required=True, help='MySQL host')
    parser.add_argument('--port', type=int, default=3306, help='MySQL port')
    parser.add_argument('--user', required=True, help='MySQL user')
    parser.add_argument('--password', required=True, help='MySQL password')
    parser.add_argument('--idle-threshold', type=int, default=IDLE_THRESHOLD_SECONDS, help='Idle time threshold in seconds')
    parser.add_argument('--max-query-time', type=int, default=MAX_QUERY_TIME_SECONDS, help='Max query time in seconds')
    parser.add_argument('--target-reduction', type=int, default=TARGET_THREAD_REDUCTION, help='Target thread reduction count')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode')
    return parser.parse_args()


def get_connection(host: str, port: int, user: str, password: str):
    try:
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=10
        )
        logger.info(f"Connected to MySQL at {host}:{port}")
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to MySQL: {e}")
        raise


def get_current_threads(conn) -> int:
    with conn.cursor() as cursor:
        cursor.execute("SHOW STATUS LIKE 'Threads_connected'")
        result = cursor.fetchone()
        count = int(result['Value'])
        logger.info(f"Current thread count: {count}")
        return count


def get_idle_connections(conn, idle_threshold: int) -> List[dict]:
    with conn.cursor() as cursor:
        query = """
            SELECT id, user, host, db, command, time, state, info
            FROM information_schema.processlist
            WHERE command = 'Sleep'
              AND time > %s
              AND id != CONNECTION_ID()
            ORDER BY time DESC
        """
        cursor.execute(query, (idle_threshold,))
        results = cursor.fetchall()
        logger.info(f"Found {len(results)} idle connections exceeding {idle_threshold}s threshold")
        return results


def get_long_running_queries(conn, max_query_time: int) -> List[dict]:
    with conn.cursor() as cursor:
        query = """
            SELECT id, user, host, db, command, time, state, LEFT(info, 100) as info
            FROM information_schema.processlist
            WHERE command != 'Sleep'
              AND time > %s
              AND id != CONNECTION_ID()
              AND user NOT IN ('system user', 'event_scheduler')
            ORDER BY time DESC
        """
        cursor.execute(query, (max_query_time,))
        results = cursor.fetchall()
        logger.info(f"Found {len(results)} long-running queries exceeding {max_query_time}s")
        return results


def kill_connections(conn, connection_ids: List[int], dry_run: bool) -> Tuple[int, int]:
    success_count = 0
    failure_count = 0
    for conn_id in connection_ids:
        try:
            if not dry_run:
                with conn.cursor() as cursor:
                    cursor.execute(f"KILL {conn_id}")
                logger.info(f"Killed connection ID: {conn_id}")
            else:
                logger.info(f"[DRY-RUN] Would kill connection ID: {conn_id}")
            success_count += 1
        except Exception as e:
            logger.warning(f"Failed to kill connection {conn_id}: {e}")
            failure_count += 1
    return success_count, failure_count


def get_max_connections(conn) -> int:
    with conn.cursor() as cursor:
        cursor.execute("SHOW VARIABLES LIKE 'max_connections'")
        result = cursor.fetchone()
        return int(result['Value'])


def adjust_max_connections(conn, current_threads: int, dry_run: bool) -> bool:
    try:
        max_conn = get_max_connections(conn)
        logger.info(f"Current max_connections setting: {max_conn}")
        
        if current_threads > (max_conn - RESERVED_CONNECTION_BUFFER):
            new_max = max_conn + 200
            if not dry_run:
                with conn.cursor() as cursor:
                    cursor.execute(f"SET GLOBAL max_connections = {new_max}")
                logger.info(f"Increased max_connections from {max_conn} to {new_max}")
            else:
                logger.info(f"[DRY-RUN] Would increase max_connections from {max_conn} to {new_max}")
            return True
        else:
            logger.info("max_connections adjustment not needed")
            return False
    except Exception as e:
        logger.warning(f"Failed to adjust max_connections: {e}")
        return False


def main():
    args = parse_args()
    
    logger.info("="*60)
    logger.info("MySQL Thread Connection Remediation Started")
    logger.info(f"Target: {args.host}:{args.port}")
    logger.info(f"Dry-run mode: {args.dry_run}")
    logger.info("="*60)
    
    try:
        conn = get_connection(args.host, args.port, args.user, args.password)
        
        initial_threads = get_current_threads(conn)
        
        if initial_threads < 500:
            logger.info(f"Thread count ({initial_threads}) is below critical threshold. No action needed.")
            conn.close()
            return 0
        
        idle_conns = get_idle_connections(conn, args.idle_threshold)
        long_queries = get_long_running_queries(conn, args.max_query_time)
        
        kill_ids = []
        
        for ic in idle_conns[:args.target_reduction]:
            kill_ids.append(ic['id'])
            logger.info(f"Marking idle connection for termination: ID={ic['id']}, User={ic['user']}, Host={ic['host']}, IdleTime={ic['time']}s")
        
        for lq in long_queries[:20]:
            if lq['id'] not in kill_ids:
                kill_ids.append(lq['id'])
                logger.info(f"Marking long query for termination: ID={lq['id']}, User={lq['user']}, Runtime={lq['time']}s, Query={lq['info']}")
        
        if kill_ids:
            success, failure = kill_connections(conn, kill_ids, args.dry_run)
            logger.info(f"Connection termination results: {success} successful, {failure} failed")
        else:
            logger.info("No connections marked for termination")
        
        time.sleep(2)
        
        final_threads = get_current_threads(conn)
        reduction = initial_threads - final_threads
        logger.info(f"Thread reduction: {reduction} (from {initial_threads} to {final_threads})")
        
        adjust_max_connections(conn, final_threads, args.dry_run)
        
        conn.close()
        
        logger.info("="*60)
        logger.info("Remediation completed successfully")
        logger.info("="*60)
        
        return 0
        
    except Exception as e:
        logger.error(f"Remediation failed: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())