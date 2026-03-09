#!/usr/bin/env python3
"""Quick SQLite connection test script."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from api import get_db_connection, initialize_database, resolve_sqlite_db_path


def test_connection() -> bool:
    db_path = resolve_sqlite_db_path()
    print(f"SQLite path: {db_path}")
    print("Connecting...")

    try:
        client = get_db_connection()
        initialize_database(client)
        print("Client created")

        result = client.execute("SELECT 1 as test")
        print(f"SELECT 1 succeeded: {result.rows}")

        result = client.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in result.rows]
        print(f"Tables in database: {tables}")

        if not tables:
            print("No tables found. Check schema.sql.")

        client.close()
        print("Connection test PASSED.")
        return True

    except Exception as e:
        print(f"Connection FAILED: {type(e).__name__}: {e}")
        return False


if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)
