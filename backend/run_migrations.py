"""
Database migration runner for AI Revenue Recovery Agent.

Usage:
    python run_migrations.py

Runs all SQL migration files in backend/migrations/ directory in order.
"""

import os
import sys
from pathlib import Path
from database import execute_query, get_connection

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

def get_applied_migrations(conn):
    """Get list of already applied migrations."""
    try:
        # Create migrations table if it doesn't exist
        execute_query("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                migration_name TEXT PRIMARY KEY,
                applied_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)

        results = execute_query(
            "SELECT migration_name FROM schema_migrations ORDER BY applied_at",
            fetch=True
        )
        return [row['migration_name'] for row in results]
    except Exception as e:
        print(f"✗ Error checking migrations: {e}")
        return []

def run_migration(conn, migration_file: Path):
    """Run a single migration file."""
    migration_name = migration_file.name

    print(f"Running migration: {migration_name}")

    try:
        # Read migration SQL
        with open(migration_file, 'r', encoding='utf-8') as f:
            sql = f.read()

        # Execute migration
        cursor = conn.cursor()
        cursor.execute(sql)

        # Record migration
        execute_query(
            "INSERT INTO schema_migrations (migration_name) VALUES (%s)",
            (migration_name,)
        )

        conn.commit()
        print(f"✓ Applied migration: {migration_name}")
        return True

    except Exception as e:
        conn.rollback()
        print(f"✗ Migration failed: {migration_name}")
        print(f"  Error: {e}")
        return False

def main():
    """Run all pending migrations."""
    print("=== Database Migration Runner ===\n")

    # Check migrations directory exists
    if not MIGRATIONS_DIR.exists():
        print(f"✗ Migrations directory not found: {MIGRATIONS_DIR}")
        sys.exit(1)

    # Get connection
    conn = get_connection()

    try:
        # Get applied migrations
        applied = get_applied_migrations(conn)
        print(f"Already applied: {len(applied)} migrations")

        # Get all migration files
        migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

        if not migration_files:
            print("No migration files found")
            return

        # Run pending migrations
        pending = [f for f in migration_files if f.name not in applied]

        if not pending:
            print("\n✓ All migrations up to date")
            return

        print(f"\nPending migrations: {len(pending)}")

        for migration_file in pending:
            success = run_migration(conn, migration_file)
            if not success:
                print("\n✗ Migration failed, stopping")
                sys.exit(1)

        print(f"\n✓ Successfully applied {len(pending)} migrations")

    except Exception as e:
        print(f"\n✗ Migration runner error: {e}")
        sys.exit(1)
    finally:
        if conn:
            from database import return_connection
            return_connection(conn)

if __name__ == "__main__":
    main()
