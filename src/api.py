"""
FastAPI application for arxiv data engine.
- SQLite-only storage with automatic schema initialization
- Backward-compatible handling for legacy TURSO_* env vars
- API_SECRET_KEY auth on business endpoints
- /health for Railway, POST /api/v1/ingest, GET /api/v1/reports
"""

import asyncio
import json
import logging
import os
import sqlite3
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_DATABASE_PATH = Path.home() / "Downloads" / "arxiv_data" / "papers.db"
DEFAULT_SCHEMA_PATH = REPO_ROOT / "schema.sql"

# ---------------------------------------------------------------------------
# Config & connection factory
# ---------------------------------------------------------------------------

def _get_api_secret_key() -> str:
    """Read at request time so tests can patch os.environ before the request."""
    return os.getenv("API_SECRET_KEY", "")


class _Sqlite3Result:
    """Minimal result adapter so callers can use .rows consistently."""
    __slots__ = ("rows",)

    def __init__(self, rows: list):
        self.rows = rows


class _Sqlite3Wrapper:
    """Thread-safe sqlite3 wrapper with execute() and .rows."""
    __slots__ = ("_conn", "_lock", "path")

    def __init__(self, path: Path):
        self.path = str(path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.commit()

    def execute(self, sql: str, args: list | None = None) -> _Sqlite3Result:
        with self._lock:
            cur = self._conn.execute(sql, args or [])
            rows = cur.fetchall()
            self._conn.commit()
        return _Sqlite3Result(rows)

    def executescript(self, sql_script: str) -> None:
        with self._lock:
            self._conn.executescript(sql_script)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def _repo_relative_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def _path_from_file_url(db_url: str) -> Path:
    path = db_url[5:] if len(db_url) > 5 else "local.db"
    if path.startswith("//"):
        return Path(path[1:]).expanduser()
    return _repo_relative_path(path)


def resolve_sqlite_db_path() -> Path:
    """
    Resolve the SQLite database path.

    Priority:
    1. SQLITE_DATABASE_PATH
    2. TURSO_DATABASE_URL when it already points to file:...
    3. ~/Downloads/arxiv_data/papers.db

    Remote libsql/http Turso URLs are ignored on purpose so Railway users do not
    need to delete legacy Variables before switching the app to SQLite.
    """
    sqlite_database_path = os.getenv("SQLITE_DATABASE_PATH", "").strip()
    if sqlite_database_path:
        return _repo_relative_path(sqlite_database_path)

    legacy_turso_url = os.getenv("TURSO_DATABASE_URL", "").strip()
    if legacy_turso_url.startswith("file:"):
        return _path_from_file_url(legacy_turso_url)

    if legacy_turso_url:
        scheme = legacy_turso_url.split(":", 1)[0]
        logger.warning(
            "Ignoring legacy TURSO_DATABASE_URL with scheme '%s'; using SQLite at %s instead. "
            "Set SQLITE_DATABASE_PATH if you want a custom SQLite location.",
            scheme,
            DEFAULT_SQLITE_DATABASE_PATH,
        )
    return DEFAULT_SQLITE_DATABASE_PATH


def get_db_connection() -> _Sqlite3Wrapper:
    db_path = resolve_sqlite_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return _Sqlite3Wrapper(db_path)


def initialize_database(client: _Sqlite3Wrapper) -> None:
    """Create required tables and seed users if schema.sql is available."""
    if not DEFAULT_SCHEMA_PATH.exists():
        raise RuntimeError(f"schema.sql not found at {DEFAULT_SCHEMA_PATH}")
    client.executescript(DEFAULT_SCHEMA_PATH.read_text(encoding="utf-8"))


def _execute_select_one(client) -> None:
    """Run SELECT 1 to warm/verify connection (sync, run in thread)."""
    client.execute("SELECT 1")


def _insert_report(client, user_id: str, theme: str, report_data: Any) -> None:
    """Sync INSERT into daily_reports; must be run via asyncio.to_thread."""
    report_id = str(uuid.uuid4())
    report_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
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
    await asyncio.to_thread(initialize_database, client)
    await asyncio.to_thread(_execute_select_one, client)
    app.state.db = client
    app.state.db_path = client.path
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
        return {"status": "unhealthy", "database": "not_initialized", "backend": "sqlite"}
    try:
        await asyncio.to_thread(_execute_select_one, db)
        return {
            "status": "ok",
            "database": "connected",
            "backend": "sqlite",
            "path": getattr(app.state, "db_path", None),
        }
    except Exception as e:
        return {"status": "unhealthy", "database": str(e), "backend": "sqlite"}


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
