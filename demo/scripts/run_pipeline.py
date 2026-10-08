#!/usr/bin/env python3
"""Run the complete GamePulse demo pipeline from raw inputs to validated report."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def call(*args: str) -> None:
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-public", action="store_true", help="Fetch a fresh public Steam review sample")
    args = parser.parse_args()
    market_raw = ROOT / "data/public/market_reviews.csv"
    call("scripts/generate_synthetic_data.py")
    if args.refresh_public or not market_raw.exists():
        call("scripts/fetch_steam_reviews.py")
    call("scripts/analyze_feedback.py", "data/synthetic/feedback.csv", "data/synthetic/feedback_annotated.csv")
    call("scripts/analyze_feedback.py", "data/public/market_reviews.csv", "data/public/market_reviews_annotated.csv", "--text-column", "review_text")
    # Replace the unannotated first-party file used by the database with the annotated version.
    (ROOT / "data/synthetic/feedback.csv").write_bytes((ROOT / "data/synthetic/feedback_annotated.csv").read_bytes())
    call("scripts/build_database.py")
    call("scripts/run_analysis.py")
    call("scripts/create_charts.py")
    call("skill/game-product-intelligence/scripts/validate_output.py", "outputs/product_intelligence.json")
    print("GamePulse pipeline completed successfully.")


if __name__ == "__main__":
    main()
