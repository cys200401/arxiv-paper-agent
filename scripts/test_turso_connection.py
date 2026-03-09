#!/usr/bin/env python3
"""Quick Turso connection test script."""
import os
import sys

# Set these or use environment variables
TURSO_DATABASE_URL = os.getenv(
    "TURSO_DATABASE_URL",
    "libsql://paper-agent-db-x1111110.aws-ap-northeast-1.turso.io"
)
TURSO_AUTH_TOKEN = os.getenv(
    "TURSO_AUTH_TOKEN",
    ""  # Paste your token here if not in env
)

def test_connection():
    try:
        import libsql_client
    except ImportError:
        print("❌ libsql-client not installed. Run: pip install libsql-client")
        return False

    version = getattr(libsql_client, "__version__", "unknown")
    print(f"libsql_client version: {version}")
    print(f"Database URL: {TURSO_DATABASE_URL}")
    print(f"Auth token: {TURSO_AUTH_TOKEN[:20]}..." if TURSO_AUTH_TOKEN else "Auth token: NOT SET")

    if not TURSO_AUTH_TOKEN:
        print("❌ TURSO_AUTH_TOKEN is not set!")
        return False

    print("\n🔄 Connecting...")
    try:
        client = libsql_client.create_client_sync(
            TURSO_DATABASE_URL,
            auth_token=TURSO_AUTH_TOKEN
        )
        print("✅ Client created")

        # Test basic query
        result = client.execute("SELECT 1 as test")
        print(f"✅ SELECT 1 succeeded: {result.rows}")

        # Check if tables exist
        result = client.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in result.rows]
        print(f"✅ Tables in database: {tables}")

        if not tables:
            print("⚠️  No tables found. You may need to run schema.sql")

        client.close()
        print("\n✅ Connection test PASSED!")
        return True

    except Exception as e:
        print(f"\n❌ Connection FAILED: {type(e).__name__}: {e}")
        return False

if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)
