from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import pandas as pd

from .schema import COLUMNS, validate_record


def save_raw_snapshot(records: Iterable[dict], output_path: Path) -> int:
    rows = list(records)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            validate_record(row)
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(rows)


def upsert_csv(records: Iterable[dict], output_path: Path) -> tuple[int, int]:
    rows = list(records)
    for row in rows:
        validate_record(row)
    incoming = pd.DataFrame(rows, columns=COLUMNS)
    if output_path.exists():
        existing = pd.read_csv(output_path)
        combined = pd.concat([existing, incoming], ignore_index=True)
    else:
        combined = incoming
    before = len(combined)
    combined = combined.drop_duplicates(subset=["record_id"], keep="last")
    combined = combined.sort_values(["source", "created_at", "record_id"], na_position="last")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(output_path, index=False)
    return len(incoming), before - len(combined)


def replace_game_csv(records: Iterable[dict], output_path: Path, game: str) -> tuple[int, int]:
    rows = list(records)
    for row in rows:
        validate_record(row)
    incoming = pd.DataFrame(rows, columns=COLUMNS)
    if output_path.exists():
        existing = pd.read_csv(output_path)
        existing = existing[existing.game.str.casefold() != game.casefold()]
        combined = pd.concat([existing, incoming], ignore_index=True)
    else:
        combined = incoming
    before = len(combined)
    combined = combined.drop_duplicates(subset=["record_id"], keep="last")
    combined = combined.sort_values(["source", "created_at", "record_id"], na_position="last")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(output_path, index=False)
    return len(incoming), before - len(combined)
