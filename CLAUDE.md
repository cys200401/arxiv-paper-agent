# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Daily Academic Paper Recommendation System that crawls arXiv papers, filters them based on user interests, generates LLM-powered bilingual summaries (English + Chinese), and stores reports in a SQLite database behind a FastAPI REST API.

## Commands

### Development

```bash
# Install dependencies
pip install -r requirements.txt
pip install -r requirements.txt -r requirements-dev.txt  # With tests

# Run crawler (outputs JSON to stdout, logs to stderr)
python src/crawler.py --query "cat:cs.AI" --max-results 100

# Run agent (reads JSON from stdin, outputs DailyReport JSON)
python src/agent.py --interest "AI agents" --top-k 5 --model qwen-turbo

# Full pipeline
python src/crawler.py | python src/agent.py --interest "cs.AI" --model gemini-2.0-flash

# CLI with file I/O
python -m src.cli.crawler --query "machine learning" --target 5 --output papers.json
python -m src.cli.agent --input papers.json --output report.json --interest "ML"

# Start API server (interactive docs at http://127.0.0.1:8000/docs)
uvicorn src.api:app --reload --host 127.0.0.1 --port 8000
```

### Testing

```bash
# Run all tests
PYTHONPATH=src pytest tests/ -v

# Run specific test file
PYTHONPATH=src pytest tests/test_crawler.py -v

# Run single test
PYTHONPATH=src pytest tests/test_agent.py::test_function_name -v

# Integration test (requires DASHSCOPE_API_KEY or GEMINI_API_KEY)
./scripts/run_integration_test.sh
```

### Database

```bash
# Optional: initialize local database manually
mkdir -p "$HOME/Downloads/arxiv_data"
sqlite3 "$HOME/Downloads/arxiv_data/papers.db" < schema.sql

# Optional: override default SQLite file location
export SQLITE_DATABASE_PATH="/absolute/path/to/app.db"
```

## Architecture

```
┌─────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│   CRAWLER       │ ───→ │    AGENT (LLM)   │ ───→ │   API (FastAPI)  │
│  (arXiv Fetch)  │ JSON │   (Summarize)    │ JSON │  (Store & Query) │
└─────────────────┘      └──────────────────┘      └──────────────────┘
```

### Core Components

| File | Purpose |
|------|---------|
| `src/crawler.py` | Fetches paper metadata from arXiv API; outputs JSON to stdout |
| `src/agent.py` | Reads JSON from stdin; uses LLM to generate summaries; outputs DailyReport JSON |
| `src/api.py` | FastAPI service for ingesting reports and querying by user_id |
| `src/cli/crawler.py`, `src/cli/agent.py` | Command-line wrappers with file I/O |

### Key Patterns

- **Unix Pipeline Philosophy**: Crawler outputs pure JSON to stdout, all logs go to stderr, Agent reads stdin. Enables composition: `crawler | agent`
- **Pydantic V2**: All data structures use `BaseModel` with `ConfigDict(extra="allow")`
- **Async/Thread Safety**: API uses `asyncio.to_thread()` for sync DB ops; Crawler and Agent use `ThreadPoolExecutor` for parallel operations
- **SQLite Only**: The API always uses SQLite. If legacy `TURSO_DATABASE_URL` or `TURSO_AUTH_TOKEN` Variables still exist on Railway, they are ignored unless `TURSO_DATABASE_URL` already points to `file:...`.
- **Retry Logic**: Crawler uses `tenacity` for automatic retries with exponential backoff on arXiv API calls

### Data Models

- `PaperModel`: Paper metadata (id, title, authors, summary, pdf_url, categories)
- `EvaluatedPaper`: LLM-evaluated paper with cn_translation, recommend_reason, tech_tags
- `DailyReport`: Final output with date, theme, top_papers list
- `IngestBody`: API request body (user_id, theme, report_data)

### LLM Providers

- **Qwen (DashScope)**: Default; requires `DASHSCOPE_API_KEY`
- **Gemini**: Alternative; requires `GEMINI_API_KEY`. Use a key from [Google AI Studio](https://aistudio.google.com/apikey) or enable Generative Language API in Google Cloud. Invalid or empty key yields `API key not valid`.
- Uses `instructor` library for structured output validation

### API Endpoints

- `GET /health` - Health probe (checks DB connection)
- `POST /api/v1/ingest` - Insert DailyReport (requires Bearer auth)
- `GET /api/v1/reports` - Query reports by user_id (requires Bearer auth)

## Environment Variables

```bash
DASHSCOPE_API_KEY    # For Qwen LLM (阿里云百炼)
GEMINI_API_KEY       # For Gemini LLM
SQLITE_DATABASE_PATH # Optional custom SQLite file path; default is ~/Downloads/arxiv_data/papers.db
TURSO_DATABASE_URL   # Optional legacy variable; ignored for remote libsql/http values
API_SECRET_KEY       # Bearer token for API authentication
```

## Deployment

Railway deployment with GitHub Actions workflows:
- `daily_pipeline.yml`: Runs daily at 00:00 UTC for 3 users (cs.AI, cs.LG, RL)
- `e2e-smoke.yml`: Manual smoke test workflow with custom topic input

## Notes

- CLI modules use relative imports (`from ..crawler import ...`)
- `instructor>=1.7.0` required for `from_provider()` support with Gemini
- `jsonref>=1.1.0` required by instructor for Gemini provider
- Model selection in agent: models starting with `qwen` use DASHSCOPE_API_KEY, others use GEMINI_API_KEY
- Database tables: `users` (id, username, topic_query) and `daily_reports` (id, user_id, report_date, theme, content_json)
