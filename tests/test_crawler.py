"""Unit tests for crawler: CLI (--query, --max-results) and _fetch_by_query with mocked fetcher."""
import json
import sys
from io import StringIO
from unittest.mock import patch, MagicMock

import pytest

from crawler import (
    PaperModel,
    ArxivFetcher,
    _fetch_by_query,
    main as crawler_main,
)


# ----- PaperModel / fetch_batch contract -----
def test_paper_model_dump_roundtrip():
    p = PaperModel(
        id="2401.00001",
        title="Test",
        authors=["A"],
        summary="S",
        published_date="2024-01-01",
        pdf_url="http://arxiv.org/pdf/2401.00001",
        primary_category="cs.AI",
        categories=["cs.AI"],
    )
    d = p.model_dump()
    assert d["id"] == "2401.00001"
    assert d["title"] == "Test"
    restored = PaperModel.model_validate(d)
    assert restored.id == p.id


# ----- _fetch_by_query -----
def test_fetch_by_query_stops_at_target():
    """_fetch_by_query returns at most target_count papers and stops when batch is empty."""
    fetcher = MagicMock(spec=ArxivFetcher)
    fetcher.delay = 0
    # First call returns 3, second returns 0 (no more)
    fetcher.fetch_batch.side_effect = [
        [
            PaperModel(
                id=f"2401.0000{i}",
                title="T",
                authors=[],
                summary="S",
                published_date="2024-01-01",
                pdf_url="http://x/pdf",
                primary_category="cs.AI",
                categories=[],
            )
            for i in range(1, 4)
        ],
        [],
    ]
    out = _fetch_by_query(fetcher, "cat:cs.AI", target_count=10, batch_size=50)
    assert len(out) == 3
    assert fetcher.fetch_batch.call_count == 2


def test_fetch_by_query_respects_target_count():
    """_fetch_by_query returns exactly target_count when batches are larger."""
    fetcher = MagicMock(spec=ArxivFetcher)
    fetcher.delay = 0
    def batch(query, start, size):
        n = min(5, size)
        return [
            PaperModel(
                id=f"2401.{start + i:05d}",
                title="T",
                authors=[],
                summary="S",
                published_date="2024-01-01",
                pdf_url="http://x/pdf",
                primary_category="cs.AI",
                categories=[],
            )
            for i in range(n)
        ]
    fetcher.fetch_batch.side_effect = batch
    out = _fetch_by_query(fetcher, "all:ML", target_count=7, batch_size=5)
    assert len(out) == 7


# ----- CLI (main) -----
def test_crawler_main_with_query_stdout_valid_json():
    """With --query, main writes valid JSON array to stdout (mock network)."""
    with patch("crawler._fetch_by_query") as mock_fetch:
        mock_fetch.return_value = [
            PaperModel(
                id="2401.00001",
                title="Test",
                authors=[],
                summary="S",
                published_date="2024-01-01",
                pdf_url="http://x/pdf",
                primary_category="cs.AI",
                categories=[],
            )
        ]
        old_stdout = sys.stdout
        try:
            sys.stdout = buf = StringIO()
            with patch("sys.argv", ["crawler.py", "--query", "cat:cs.AI", "--max-results", "5"]):
                crawler_main()
            out = buf.getvalue()
        finally:
            sys.stdout = old_stdout
        data = json.loads(out)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["id"] == "2401.00001"
        mock_fetch.assert_called_once()
        call_kw = mock_fetch.call_args
        assert call_kw[0][1] == "cat:cs.AI"
        assert call_kw[0][2] == 5
