"""
Production-grade FastAPI application for arxiv data engine.
- Lifespan with DB connection warm-up (SELECT 1)
- Smart connection factory (file: local, http(s) -> libsql:// + auth)
- API_SECRET_KEY auth on all business endpoints
- /health for Railway, POST /api/v1/ingest, GET /api/v1/reports (async via to_thread)
"""

import asyncio
import json
import logging
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Any

logger = logging.getLogger(__name__)

try:
    import libsql_client
    try:
        # Log libsql_client version at startup to debug 505 errors on Railway
        version = getattr(libsql_client, "__version__", "unknown")
        logger.info(f"libsql_client version: {version}")
    except Exception as e:  # pragma: no cover - best-effort diagnostics
        logger.warning(f"Cannot check libsql_client version: {e}")
except ImportError:
    libsql_client = None  # type: ignore[misc, assignment]

from fastapi import FastAPI, Header, HTTPException, Depends, Query
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Config & connection factory
# ---------------------------------------------------------------------------

def _get_api_secret_key() -> str:
    """Read at request time so tests can patch os.environ before the request."""
    return os.getenv("API_SECRET_KEY", "")


class _Sqlite3Result:
    """Minimal result adapter so .rows works like libsql_client ResultSet."""
    __slots__ = ("rows",)
    def __init__(self, rows: list):
        self.rows = rows


class _Sqlite3Wrapper:
    """Stdlib sqlite3 wrapper with libsql_client-like execute() and .rows (for file: when libsql_client not installed)."""
    __slots__ = ("_conn",)

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def execute(self, sql: str, args: list | None = None) -> _Sqlite3Result:
        cur = self._conn.execute(sql, args or [])
        return _Sqlite3Result(cur.fetchall())

    def close(self) -> None:
        self._conn.close()


def get_db_connection():  # -> libsql_client.Client | _Sqlite3Wrapper
    """
    Smart connection factory: reads TURSO_DATABASE_URL.
    - file: -> connect locally (sqlite3 if libsql_client not installed, else libsql_client).
    - http(s): -> convert to libsql:// and connect with TURSO_AUTH_TOKEN (requires libsql_client).
    """
    db_url = os.getenv("TURSO_DATABASE_URL", "file:local.db").strip()
    auth_token = os.getenv("TURSO_AUTH_TOKEN", "").strip()

    if db_url.startswith("file:"):
        if libsql_client is not None:
            return libsql_client.create_client_sync(db_url)
        path = db_url[5:] if len(db_url) > 5 else "local.db"
        if path.startswith("//"):
            path = path[1:]  # file:///tmp/db -> /tmp/db
        return _Sqlite3Wrapper(sqlite3.connect(path))

    if libsql_client is None:
        raise RuntimeError("Remote Turso requires: pip install libsql-client")
    if db_url.startswith("http://") or db_url.startswith("https://"):
        db_url = db_url.replace("https://", "libsql://").replace("http://", "libsql://")
    return libsql_client.create_client_sync(db_url, auth_token=auth_token)


def _execute_select_one(client) -> None:
    """Run SELECT 1 to warm/verify connection (sync, run in thread)."""
    client.execute("SELECT 1")


def _insert_report(client, user_id: str, theme: str, report_data: Any) -> None:
    """Sync INSERT into daily_reports; must be run via asyncio.to_thread."""
    report_id = str(uuid.uuid4())
    report_date = datetime.utcnow().strftime("%Y-%m-%d")
    content_json = json.dumps(report_data) if not isinstance(report_data, str) else report_data
    client.execute(
        "INSERT INTO daily_reports (id, user_id, report_date, theme, content_json) VALUES (?, ?, ?, ?, ?)",
        [report_id, user_id, report_date, theme, content_json],
    )


def _fetch_reports(client, user_id: str, limit: int) -> list[dict]:
    """Sync query reports by user_id, date desc, limit; run via asyncio.to_thread."""
    rs = client.execute(
        "SELECT id, user_id, report_date, theme, content_json, created_at FROM daily_reports WHERE user_id = ? ORDER BY report_date DESC, created_at DESC LIMIT ?",
        [user_id, limit],
    )
    rows = []
    for row in rs.rows:
        rows.append({
            "id": row[0],
            "user_id": row[1],
            "report_date": row[2],
            "theme": row[3],
            "content_json": row[4],
            "created_at": row[5],
        })
    return rows


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

async def verify_api_key(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    api_secret_key = _get_api_secret_key()
    if not api_secret_key:
        raise HTTPException(status_code=500, detail="API_SECRET_KEY not configured")
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.removeprefix("Bearer ").strip() if authorization else ""
    if token != api_secret_key:
        raise HTTPException(status_code=403, detail="Invalid API key")


# ---------------------------------------------------------------------------
# Lifespan: connection warm-up and teardown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    client = await asyncio.to_thread(get_db_connection)
    await asyncio.to_thread(_execute_select_one, client)
    app.state.db = client
    yield
    if hasattr(app.state, "db") and app.state.db is not None:
        client = app.state.db
        app.state.db = None
        close_fn = getattr(client, "close", None)
        if callable(close_fn):
            try:
                close_fn()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# App and routes
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Arxiv Data Engine API",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    """Health probe for Railway: returns DB connection status."""
    db = getattr(app.state, "db", None)
    if db is None:
        return {"status": "unhealthy", "database": "not_initialized"}
    try:
        await asyncio.to_thread(_execute_select_one, db)
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": str(e)}


# ----- Ingest -----

class IngestBody(BaseModel):
    user_id: str = Field(..., min_length=1)
    theme: str = Field(..., min_length=1)
    report_data: Any = Field(...)


@app.post("/api/v1/ingest", dependencies=[Depends(verify_api_key)])
async def ingest(body: IngestBody):
    """Async non-blocking write: INSERT via asyncio.to_thread."""
    db = getattr(app.state, "db", None)
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    try:
        await asyncio.to_thread(_insert_report, db, body.user_id, body.theme, body.report_data)
    except Exception:
        raise HTTPException(status_code=503, detail="Database not available")
    return {"ok": True, "user_id": body.user_id, "theme": body.theme}


# ----- Reports -----

@app.get("/api/v1/reports", dependencies=[Depends(verify_api_key)])
async def reports(
    user_id: Annotated[str, Query(min_length=1)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    """Safe query by user_id, date desc, with limit; fetch via asyncio.to_thread."""
    db = getattr(app.state, "db", None)
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    rows = await asyncio.to_thread(_fetch_reports, db, user_id, limit)
    return {"user_id": user_id, "reports": rows, "count": len(rows)}
