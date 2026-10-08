from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


COLUMNS = [
    "record_id",
    "source",
    "source_type",
    "game",
    "channel",
    "content_type",
    "source_content_id",
    "parent_id",
    "created_at",
    "collected_at",
    "title",
    "text",
    "url",
    "language",
    "recommended",
    "rating",
    "engagement_score",
    "reply_count",
    "playtime_hours",
    "metadata_json",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(source: str, source_content_id: str) -> str:
    return hashlib.sha256(f"{source}:{source_content_id}".encode()).hexdigest()[:20]


def record(**values: Any) -> dict[str, Any]:
    source = str(values["source"])
    source_content_id = str(values["source_content_id"])
    base = {column: None for column in COLUMNS}
    base.update(values)
    base["record_id"] = stable_id(source, source_content_id)
    base["collected_at"] = values.get("collected_at") or utc_now()
    metadata = base.get("metadata_json")
    if isinstance(metadata, (dict, list)):
        base["metadata_json"] = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
    return base


def validate_record(item: dict[str, Any]) -> None:
    missing = [key for key in ["source", "source_type", "game", "source_content_id", "created_at", "text"] if not item.get(key)]
    if missing:
        raise ValueError(f"Record missing required fields: {', '.join(missing)}")
    extra = set(item) - set(COLUMNS)
    if extra:
        raise ValueError(f"Record has unexpected fields: {', '.join(sorted(extra))}")
