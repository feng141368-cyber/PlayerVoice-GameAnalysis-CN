#!/usr/bin/env python3
"""Fetch a privacy-minimized sample of public Steam reviews for market context."""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd


APPS = {"Tower of Fantasy": 2064650, "Palia": 2707930}
ENDPOINT = "https://store.steampowered.com/appreviews/{app_id}"


def fetch_app(app_name: str, app_id: int, limit: int) -> list[dict]:
    rows: list[dict] = []
    cursor = "*"
    while len(rows) < limit:
        params = urllib.parse.urlencode(
            {"json": 1, "filter": "recent", "language": "english", "num_per_page": min(100, limit - len(rows)),
             "purchase_type": "all", "cursor": cursor}
        )
        request = urllib.request.Request(
            f"{ENDPOINT.format(app_id=app_id)}?{params}",
            headers={"User-Agent": "GamePulse portfolio project/1.0"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
        for review in payload.get("reviews", []):
            rows.append(
                {"source": "Steam", "app_id": app_id, "app_name": app_name,
                 "created_at": pd.to_datetime(review.get("timestamp_created"), unit="s", utc=True).isoformat(),
                 "voted_up": bool(review.get("voted_up")),
                 "playtime_hours": round(review.get("author", {}).get("playtime_forever", 0) / 60, 1),
                 "review_text": " ".join(review.get("review", "").split())}
            )
        next_cursor = payload.get("cursor")
        if not payload.get("reviews") or not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor
        time.sleep(0.35)
    return rows[:limit]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("data/public/market_reviews.csv"))
    parser.add_argument("--per-app", type=int, default=100)
    args = parser.parse_args()
    rows = []
    for app_name, app_id in APPS.items():
        rows.extend(fetch_app(app_name, app_id, args.per_app))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    frame.insert(0, "market_review_id", [f"M{i:04d}" for i in range(1, len(frame) + 1)])
    frame.to_csv(args.output, index=False)
    print(f"Saved {len(rows)} public reviews to {args.output}")


if __name__ == "__main__":
    main()
