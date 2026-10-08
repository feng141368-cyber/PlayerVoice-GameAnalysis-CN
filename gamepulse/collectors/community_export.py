from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from ..schema import record


def _iso(value: Any) -> str:
    timestamp = pd.to_datetime(value, utc=True, errors="raise")
    return timestamp.isoformat()


def collect_community_export(game: str, path: Path, platform: str = "discord") -> list[dict[str, Any]]:
    """Import an authorized DiscordChatExporter JSON or a normalized CSV export."""
    rows: list[dict[str, Any]] = []
    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path)
        required = {"id", "timestamp", "content"}
        if not required.issubset(frame.columns):
            raise ValueError(f"CSV export requires columns: {', '.join(sorted(required))}")
        for item in frame.to_dict("records"):
            if not str(item.get("content", "")).strip():
                continue
            rows.append(
                record(
                    source=platform, source_type="authorized_community_export", game=game,
                    channel=str(item.get("channel", path.stem)), content_type="message",
                    source_content_id=str(item["id"]), parent_id=item.get("reply_to"),
                    created_at=_iso(item["timestamp"]), title=None, text=str(item["content"]).strip(),
                    url=item.get("url"), language=item.get("language"), recommended=None, rating=None,
                    engagement_score=int(item.get("reactions", 0) or 0), reply_count=0,
                    playtime_hours=None, metadata_json={"import_file": path.name},
                )
            )
        return rows

    payload = json.loads(path.read_text(encoding="utf-8"))
    channel = payload.get("channel", {}).get("name", path.stem)
    for item in payload.get("messages", []):
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        reactions = sum(int(reaction.get("count", 0)) for reaction in item.get("reactions", []))
        reference = item.get("reference") or {}
        rows.append(
            record(
                source=platform, source_type="authorized_community_export", game=game,
                channel=channel, content_type="message", source_content_id=str(item["id"]),
                parent_id=reference.get("messageId"), created_at=_iso(item["timestamp"]),
                title=None, text=content, url=None, language=None, recommended=None, rating=None,
                engagement_score=reactions, reply_count=0, playtime_hours=None,
                metadata_json={"import_file": path.name},
            )
        )
    return rows
