import os
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Connection pool configuration
MIN_CONNECTIONS = 2
MAX_CONNECTIONS = 20
CONNECTION_TIMEOUT_SECONDS = 5

# Initialize connection pool (thread-safe)
_connection_pool = None

def get_pool():
    """Get or create the connection pool (singleton pattern)."""
    global _connection_pool

    if _connection_pool is None:
        try:
            _connection_pool = psycopg2.pool.ThreadedConnectionPool(
                MIN_CONNECTIONS,
                MAX_CONNECTIONS,
                DATABASE_URL,
                cursor_factory=RealDictCursor,
                connect_timeout=CONNECTION_TIMEOUT_SECONDS
            )
            print(f"✓ Database connection pool initialized: {MIN_CONNECTIONS}-{MAX_CONNECTIONS} connections")
        except Exception as e:
            print(f"✗ Failed to initialize connection pool: {e}")
            raise

    return _connection_pool

def get_connection():
    """Get a connection from the pool."""
    pool_instance = get_pool()
    try:
        conn = pool_instance.getconn()
        if conn is None:
            raise Exception("Failed to get connection from pool")
        return conn
    except Exception as e:
        print(f"⚠ Error getting connection from pool: {e}")
        raise

def return_connection(conn):
    """Return a connection to the pool."""
    if conn:
        try:
            get_pool().putconn(conn)
        except Exception as e:
            print(f"⚠ Error returning connection to pool: {e}")
            # If putconn fails, close the connection directly
            try:
                conn.close()
            except:
                pass

def execute_query(query, params=None, fetch=False):
    """
    Execute a query using a pooled connection.

    Connection is automatically returned to pool after use.
    """
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            if fetch:
                result = cursor.fetchall()
                conn.commit()
                return result
            conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if conn:
            return_connection(conn)

def close_pool():
    """Close all connections in the pool (call on shutdown)."""
    global _connection_pool
    if _connection_pool:
        _connection_pool.closeall()
        print("✓ Database connection pool closed")
        _connection_pool = None

