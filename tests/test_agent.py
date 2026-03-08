"""Unit tests for agent: _read_json_input, _normalize_papers, DailyReport schema."""
import json
import tempfile
from pathlib import Path

import pytest

from agent import (
    _read_json_input,
    _normalize_papers,
    DailyReport,
    EvaluatedPaper,
)


def test_normalize_papers_list():
    """List of paper dicts with title/summary is accepted."""
    payload = [
        {"id": "1", "title": "T1", "summary": "S1"},
        {"id": "2", "title": "T2", "summary": "S2", "extra": "x"},
    ]
    out = _normalize_papers(payload)
    assert len(out) == 2
    assert out[0]["title"] == "T1"
    assert out[1].get("extra") == "x"


def test_normalize_papers_dict_with_papers_key():
    """Dict with 'papers' key is unwrapped."""
    payload = {"papers": [{"title": "T", "summary": "S"}]}
    out = _normalize_papers(payload)
    assert len(out) == 1
    assert out[0]["title"] == "T"


def test_normalize_papers_dict_with_data_key():
    """Dict with 'data' key is unwrapped."""
    payload = {"data": [{"title": "T", "summary": "S"}]}
    out = _normalize_papers(payload)
    assert len(out) == 1


def test_normalize_papers_rejects_non_list():
    with pytest.raises(TypeError, match="list"):
        _normalize_papers({"x": 1})


def test_normalize_papers_skips_missing_title_summary():
    payload = [
        {"title": "T", "summary": "S"},
        {"title": "T2"},  # no summary
        {"summary": "S3"},  # no title
    ]
    out = _normalize_papers(payload)
    assert len(out) == 1
    assert out[0]["title"] == "T"


def test_read_json_input_from_file():
    """_read_json_input reads from file when path is given."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump([{"title": "T", "summary": "S"}], f)
        path = f.name
    try:
        out = _read_json_input(path)
        assert isinstance(out, list)
        assert out[0]["title"] == "T"
    finally:
        Path(path).unlink(missing_ok=True)


def test_daily_report_schema_parse():
    """DailyReport and EvaluatedPaper parse from ingest-style JSON."""
    raw = {
        "date": "2024-01-15",
        "theme": "cat:cs.AI",
        "top_papers": [
            {
                "title": "Paper 1",
                "original_summary": "Abstract here.",
                "cn_translation": "摘要",
                "recommend_reason": "Good.",
                "tech_tags": ["ML", "NLP", "LLM"],
            }
        ],
    }
    report = DailyReport.model_validate(raw)
    assert report.date == "2024-01-15"
    assert report.theme == "cat:cs.AI"
    assert len(report.top_papers) == 1
    assert report.top_papers[0].title == "Paper 1"
    assert report.top_papers[0].tech_tags == ["ML", "NLP", "LLM"]


def test_daily_report_json_roundtrip():
    """DailyReport serializes to JSON that API ingest expects as report_data."""
    report = DailyReport(
        date="2024-01-15",
        theme="cs.AI",
        top_papers=[
            EvaluatedPaper(
                title="T",
                original_summary="S",
                cn_translation="中文",
                recommend_reason="R",
                tech_tags=["A", "B", "C"],
            )
        ],
    )
    d = report.model_dump()
    assert "date" in d and "theme" in d and "top_papers" in d
    # Must be JSON-serializable (no bytes, etc.)
    json_str = json.dumps(d, ensure_ascii=False)
    back = json.loads(json_str)
    DailyReport.model_validate(back)
