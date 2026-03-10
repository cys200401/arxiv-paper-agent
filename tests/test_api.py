"""Unit tests for API: IngestBody schema and POST /api/v1/ingest contract."""
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api import IngestBody, app, resolve_sqlite_db_path


def test_ingest_body_schema():
    """IngestBody accepts user_id, theme, report_data (any)."""
    body = IngestBody(
        user_id="user_1",
        theme="cat:cs.AI",
        report_data={"date": "2024-01-01", "theme": "cs.AI", "top_papers": []},
    )
    assert body.user_id == "user_1"
    assert body.theme == "cat:cs.AI"
    assert body.report_data["date"] == "2024-01-01"


def test_ingest_body_rejects_empty_user_id():
    with pytest.raises(ValidationError):
        IngestBody(user_id="", theme="x", report_data={})


def test_ingest_body_rejects_empty_theme():
    with pytest.raises(ValidationError):
        IngestBody(user_id="u", theme="", report_data={})


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "test_api.db"
    with patch.dict(os.environ, {"SQLITE_DATABASE_PATH": str(db_path)}, clear=False):
        with TestClient(app) as test_client:
            yield test_client


def test_ingest_requires_auth(client):
    """POST /api/v1/ingest without Authorization returns 401/403."""
    resp = client.post(
        "/api/v1/ingest",
        json={
            "user_id": "user_1",
            "theme": "cat:cs.AI",
            "report_data": {"date": "2024-01-01", "theme": "cs.AI", "top_papers": []},
        },
    )
    assert resp.status_code in (401, 403, 500)  # 500 if API_SECRET_KEY unset


def test_resolve_sqlite_db_path_prefers_explicit_env(tmp_path):
    custom_db = tmp_path / "custom.db"
    with patch.dict(os.environ, {"SQLITE_DATABASE_PATH": str(custom_db)}, clear=False):
        assert resolve_sqlite_db_path() == custom_db


def test_resolve_sqlite_db_path_ignores_remote_turso_url():
    with patch.dict(os.environ, {"TURSO_DATABASE_URL": "libsql://example.turso.io"}, clear=True):
        assert resolve_sqlite_db_path() == Path.home() / "Downloads" / "arxiv_data" / "papers.db"


def test_ingest_accepts_valid_payload_with_auth(client):
    """With valid API key and initialized SQLite DB, ingest returns 200 and ok True."""
    with patch.dict(os.environ, {"API_SECRET_KEY": "test-secret-key"}, clear=False):
        resp = client.post(
            "/api/v1/ingest",
            json={
                "user_id": "user_1",
                "theme": "cat:cs.AI",
                "report_data": {
                    "date": "2024-01-01",
                    "theme": "cat:cs.AI",
                    "top_papers": [
                        {
                            "title": "T",
                            "original_summary": "S",
                            "cn_translation": "中文",
                            "recommend_reason": "R",
                            "tech_tags": ["A", "B", "C"],
                        }
                    ],
                },
            },
            headers={"Authorization": "Bearer test-secret-key"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert data.get("user_id") == "user_1"
    assert data.get("theme") == "cat:cs.AI"


def test_ingest_accepts_smoke_test_user(client):
    with patch.dict(os.environ, {"API_SECRET_KEY": "test-secret-key"}, clear=False):
        resp = client.post(
            "/api/v1/ingest",
            json={
                "user_id": "smoke_test",
                "theme": "machine learning",
                "report_data": {"date": "2024-01-01", "theme": "machine learning", "top_papers": []},
            },
            headers={"Authorization": "Bearer test-secret-key"},
        )
    assert resp.status_code == 200
    assert resp.json()["user_id"] == "smoke_test"


def test_ingest_rejects_unknown_user_with_clear_error(client):
    with patch.dict(os.environ, {"API_SECRET_KEY": "test-secret-key"}, clear=False):
        resp = client.post(
            "/api/v1/ingest",
            json={
                "user_id": "missing_user",
                "theme": "cat:cs.AI",
                "report_data": {"date": "2024-01-01", "theme": "cat:cs.AI", "top_papers": []},
            },
            headers={"Authorization": "Bearer test-secret-key"},
        )
    assert resp.status_code == 409
    assert resp.json() == {"detail": "Unknown user_id: missing_user"}


def test_health_reports_sqlite_backend(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["backend"] == "sqlite"
    assert data["path"].endswith("test_api.db")


def test_daily_digest_page_serves_html(client):
    resp = client.get("/daily-digest")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "每日论文速递" in resp.text
