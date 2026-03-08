"""
CLI entry point for the arXiv agent.
Run with: python -m src.cli.agent --input papers.json --output report.json [--interest "..." --model gemini-2.0-flash]
"""
import argparse
import sys

from ..agent import run_agent


def main() -> int:
    parser = argparse.ArgumentParser(description="arXiv agent: read papers JSON, output DailyReport JSON.")
    parser.add_argument("--input", "-i", required=True, help="Input papers JSON file path.")
    parser.add_argument("--output", "-o", default=None, help="Output report JSON file; if omitted, print to stdout.")
    parser.add_argument(
        "--interest",
        default="machine learning",
        help="Theme/interest for filtering and report (default: machine learning).",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Number of papers to evaluate (default: 5).")
    parser.add_argument(
        "--model",
        default="gemini-2.0-flash",
        help="LLM model: gemini-2.0-flash (default) or qwen-turbo / qwen-plus.",
    )
    args = parser.parse_args()

    try:
        report = run_agent(
            input_path=args.input,
            interest=args.interest,
            top_k=args.top_k,
            llm_model=args.model,
        )
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 1

    payload = report.model_dump_json(indent=2, by_alias=True)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(payload)
            f.write("\n")
        return 0
    sys.stdout.write(payload)
    sys.stdout.write("\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
