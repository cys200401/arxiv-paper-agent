#!/usr/bin/env bash
# Run crawler | agent with small limits and validate JSON (DailyReport).
# Usage: from repo root, ./scripts/run_integration_test.sh
# Requires: DASHSCOPE_API_KEY（千问）or GEMINI_API_KEY in env.

set -e
cd "$(dirname "$0")/.."
if [ -n "$DASHSCOPE_API_KEY" ]; then
  MODEL="qwen-turbo"
elif [ -n "$GEMINI_API_KEY" ] || [ -n "$GOOGLE_API_KEY" ]; then
  MODEL="gemini-2.0-flash"
else
  echo "Need DASHSCOPE_API_KEY or GEMINI_API_KEY in env."
  exit 1
fi
OUTPUT=$(python src/crawler.py --query "cat:cs.AI" --max-results 5 \
  | python src/agent.py --interest "cs.AI" --top-k 2 --model "$MODEL")
echo "$OUTPUT" | python -c "
import json, sys
from pathlib import Path
sys.path.insert(0, 'src')
from agent import DailyReport
data = json.load(sys.stdin)
report = DailyReport.model_validate(data)
assert report.date and report.theme and isinstance(report.top_papers, list)
print('OK: DailyReport valid, top_papers =', len(report.top_papers))
"
