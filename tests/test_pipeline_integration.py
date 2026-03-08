"""Integration test: run crawler | agent (small --max-results and --top-k), validate DailyReport JSON.
Requires GEMINI_API_KEY (or DASHSCOPE_API_KEY for qwen) in env; skips if missing."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from agent import DailyReport


def _has_llm_key() -> bool:
    return bool(
        os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or os.environ.get("DASHSCOPE_API_KEY")
    )


def _agent_model() -> str:
    """Prefer 千问 when DASHSCOPE_API_KEY set, else Gemini."""
    if os.environ.get("DASHSCOPE_API_KEY"):
        return "qwen-turbo"
    return "gemini-2.0-flash"


@pytest.mark.skipif(not _has_llm_key(), reason="GEMINI_API_KEY or DASHSCOPE_API_KEY not set")
def test_crawler_pipe_agent_produces_daily_report():
    """Run: crawler --query cat:cs.AI --max-results 5 | agent --interest 'cs.AI' --top-k 2; assert stdout is valid DailyReport."""
    repo_root = Path(__file__).resolve().parent.parent
    crawler_cmd = [sys.executable, "src/crawler.py", "--query", "cat:cs.AI", "--max-results", "5"]
    model = _agent_model()
    agent_cmd = [sys.executable, "src/agent.py", "--interest", "cs.AI", "--top-k", "2", "--model", model]
    env = os.environ.copy()
    if not env.get("GEMINI_API_KEY") and env.get("GOOGLE_API_KEY"):
        env.setdefault("GEMINI_API_KEY", env["GOOGLE_API_KEY"])

    p_crawler = subprocess.Popen(
        crawler_cmd,
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    p_agent = subprocess.Popen(
        agent_cmd,
        cwd=repo_root,
        stdin=p_crawler.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    p_crawler.stdout.close()
    out, err = p_agent.communicate(timeout=120)
    p_crawler.wait(timeout=5)

    assert p_agent.returncode == 0, f"agent stderr: {err.decode()}"
    raw = out.decode("utf-8").strip()
    assert raw, "agent produced empty stdout"
    data = json.loads(raw)
    report = DailyReport.model_validate(data)
    assert report.date
    assert report.theme
    assert isinstance(report.top_papers, list)
    for p in report.top_papers:
        assert p.title is not None
        assert "original_summary" in p.model_dump()
        assert "cn_translation" in p.model_dump()
        assert "tech_tags" in p.model_dump()
