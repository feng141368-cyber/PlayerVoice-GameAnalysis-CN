#!/usr/bin/env python3
"""Build a portable SQLite database from project CSV files."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd


def build(data_dir: Path, market_reviews: Path, database: Path) -> None:
    database.parent.mkdir(parents=True, exist_ok=True)
    if database.exists():
        database.unlink()
    with sqlite3.connect(database) as connection:
        for name in ["players", "sessions", "payments", "gameplay_events", "feedback"]:
            pd.read_csv(data_dir / f"{name}.csv").to_sql(name, connection, index=False, if_exists="replace")
        if market_reviews.exists():
            pd.read_csv(market_reviews).to_sql("market_reviews", connection, index=False, if_exists="replace")
        connection.executescript(
            """
            CREATE INDEX idx_sessions_player_date ON sessions(player_id, session_date);
            CREATE INDEX idx_payments_player_date ON payments(player_id, payment_date);
            CREATE INDEX idx_events_player_date ON gameplay_events(player_id, event_date);
            CREATE INDEX idx_feedback_patch ON feedback(patch_version);
            """
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data/synthetic"))
    parser.add_argument("--market-reviews", type=Path, default=Path("data/public/market_reviews_annotated.csv"))
    parser.add_argument("--database", type=Path, default=Path("outputs/gamepulse.db"))
    args = parser.parse_args()
    build(args.data_dir, args.market_reviews, args.database)
    print(f"Built {args.database}")


if __name__ == "__main__":
    main()
