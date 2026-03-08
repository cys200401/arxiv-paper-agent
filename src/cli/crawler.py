"""
CLI entry point for the arXiv crawler.
Run with: python -m src.cli.crawler --query "machine learning" --target 5 --output papers.json
Supports --target (alias for max-results) and --output (write JSON to file); without --output prints to stdout.
"""
import argparse
import json
import logging
import sys

from ..crawler import ArxivFetcher, _fetch_by_query


def main() -> None:
    parser = argparse.ArgumentParser(description="arXiv crawler CLI: fetch papers and output JSON.")
    parser.add_argument("--query", required=True, help="arXiv search query (e.g. 'machine learning', 'cat:cs.AI').")
    parser.add_argument(
        "--target",
        type=int,
        default=5,
        metavar="N",
        help="Max number of papers to fetch (default: 5).",
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="FILE",
        help="Write JSON to this file; if omitted, print to stdout.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    fetcher = ArxivFetcher(delay=3.0)
    papers = _fetch_by_query(fetcher, args.query, args.target)
    data = [p.model_dump() for p in papers]
    payload = json.dumps(data, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(payload)
        logging.info("Wrote %d papers to %s", len(papers), args.output)
    else:
        sys.stdout.write(payload)
        sys.stdout.flush()


if __name__ == "__main__":
    main()
