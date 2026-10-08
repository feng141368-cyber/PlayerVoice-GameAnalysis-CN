#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def validate(manifest: dict, summary: dict) -> list[str]:
    errors: list[str] = []
    collected = {name: item for name, item in manifest.get("sources", {}).items() if item.get("status") == "collected"}
    collected_total = sum(int(item.get("records", 0)) for item in collected.values())
    if not collected:
        errors.append("At least one real source must have status=collected.")
    if collected_total != int(manifest.get("total_records", -1)):
        errors.append("Manifest total_records does not match collected source counts.")
    if int(summary.get("records", -1)) < collected_total:
        errors.append("Analysis summary contains fewer records than the latest collected run.")
    if int(summary.get("sources", -1)) < len(collected):
        errors.append("Analysis summary source count is lower than the collected source count.")
    for topic in summary.get("topics", []):
        if topic.get("topic") == "Other" and topic.get("priority") != "N/A":
            errors.append("Other must not receive a product priority.")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("summary", type=Path)
    args = parser.parse_args()
    errors = validate(json.loads(args.manifest.read_text()), json.loads(args.summary.read_text()))
    if errors:
        print("Validation failed:")
        for error in errors:
            print(f"- {error}")
        sys.exit(1)
    print("Validation passed: collected-source and analysis claims are consistent.")


if __name__ == "__main__":
    main()
