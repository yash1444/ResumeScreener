"""CLI entry point:  python main.py --input ./resumes --output ./output/results.json"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from resume_screener.config import Settings  # noqa: E402
from resume_screener.pipeline import run_pipeline, to_spec_list  # noqa: E402
from resume_screener.html_report import write_reports  # noqa: E402
from resume_screener.report import print_report  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="AI resume screening & ranking")
    ap.add_argument("--input", "-i", type=Path, default=Path("resumes"), help="folder of resumes (pdf/docx/txt)")
    ap.add_argument("--output", "-o", type=Path, default=Path("output/results.json"))
    ap.add_argument("--no-llm", action="store_true", help="rule-based scoring only")
    ap.add_argument("--no-second-opinion", action="store_true", help="skip the LLM second opinion on borderline eligibility")
    ap.add_argument("--no-llm-cache", action="store_true", help="always call the LLM (ignore and do not update .cache/llm.json)")
    ap.add_argument("--top", type=int, default=10, help="rows to print in the terminal report")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    settings = Settings(second_opinion_enabled=not args.no_second_opinion, llm_cache_enabled=not args.no_llm_cache)
    try:
        results = run_pipeline(args.input, settings, analyzer=None if args.no_llm else "auto")
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    list_path = args.output.with_name(args.output.stem + "_list" + args.output.suffix)
    list_path.write_text(json.dumps(to_spec_list(results), indent=2, ensure_ascii=False), encoding="utf-8")
    report_dir = write_reports(results, args.output.parent)
    print_report(results, args.top)
    print(f"\nFull results written to {args.output}")
    print(f"Ranked candidates in the assignment's list format written to {list_path}")
    print(f"HTML reports (one per resume, plus index.html) written to {report_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
