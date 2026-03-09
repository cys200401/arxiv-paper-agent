# Repository Guidelines

## Project Structure & Module Organization
Core application code lives in `src/`. `src/crawler.py` fetches arXiv metadata and downloads PDFs, `src/agent.py` turns paper JSON into a `DailyReport`, and `src/api.py` exposes the FastAPI ingestion/report API. CLI wrappers live in `src/cli/` for file-based workflows. Tests are under `tests/` and mirror the main modules: `test_crawler.py`, `test_agent.py`, `test_api.py`, and `test_pipeline_integration.py`. Automation lives in `.github/workflows/`, helper scripts in `scripts/`, and the database schema in `schema.sql`. The default SQLite file is `~/Downloads/arxiv_data/papers.db` (for your machine: `/Users/chenyushi/Downloads/arxiv_data/papers.db`); treat database files, `papers.json`, `papers_dataset.json`, and `papers_pdf/` as local artifacts, not source files.

## Build, Test, and Development Commands
Install dependencies with `pip install -r requirements.txt -r requirements-dev.txt`.
Run the API locally with `uvicorn src.api:app --reload`.
Fetch papers with `python -m src.cli.crawler --query "cat:cs.AI" --target 5 --output papers.json`.
Generate a report with `python -m src.cli.agent --input papers.json --interest "cat:cs.AI" --output report.json`.
Run the end-to-end pipeline with `python src/crawler.py --query "cat:cs.AI" --max-results 5 | python src/agent.py --interest "cs.AI" --top-k 2 --model qwen-turbo`.
Execute tests with `pytest`. For the live LLM smoke path, use `./scripts/run_integration_test.sh`.

## Coding Style & Naming Conventions
Use Python with 4-space indentation, type hints where practical, and `snake_case` for functions, variables, and module-level helpers. Keep Pydantic models and FastAPI request/response contracts explicit. Follow the existing import grouping style: standard library, third-party packages, then local imports. There is no formatter configured in this repo, so match the surrounding file style and keep comments brief and purposeful. For CLI code, preserve the current pattern of sending structured JSON to `stdout` and logs/errors to `stderr`.

## Testing Guidelines
Pytest is configured in `pytest.ini` with `src` on `PYTHONPATH`; name files `test_*.py` and functions `test_*`. Prefer fast unit tests with mocks for network or DB access. Add integration coverage only when the behavior crosses module boundaries. `tests/test_pipeline_integration.py` and `scripts/run_integration_test.sh` require `DASHSCOPE_API_KEY`, `GEMINI_API_KEY`, or `GOOGLE_API_KEY`.

## Commit & Pull Request Guidelines
Recent history favors short, imperative commits, often with Conventional Commit prefixes such as `fix:` and `ci:`. Keep subjects specific, for example `fix: pin instructor>=1.7.0 for from_provider support`. PRs should describe the affected flow (`crawler`, `agent`, `api`, or CI), list required env vars or schema changes, and include the exact verification command you ran. If an API contract or workflow output changes, include a sample request/response or log snippet.
