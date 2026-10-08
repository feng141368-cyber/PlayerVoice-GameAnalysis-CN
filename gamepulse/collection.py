from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .collectors import (
    collect_bilibili,
    collect_bilibili_result,
    collect_douyin,
    collect_reddit,
    collect_steam,
    collect_steam_result,
    collect_weibo,
    collect_xiaohongshu,
    collect_youtube,
)
from .collectors.base import SourceStatus, evidence_to_legacy_row
from .http import CollectionError
from .storage import replace_game_csv, save_raw_snapshot, upsert_csv


COLLECTORS = {
    "steam": collect_steam,
    "bilibili": collect_bilibili,
    "reddit": collect_reddit,
    "youtube": collect_youtube,
    "weibo": collect_weibo,
    "xiaohongshu": collect_xiaohongshu,
    "douyin": collect_douyin,
}

ADAPTER_RESULT_COLLECTORS = {
    "steam": collect_steam_result,
    "bilibili": collect_bilibili_result,
}


def collect(config: dict[str, Any], root: Path, selected: set[str] | None = None, strict: bool = False, replace_game: bool = False) -> dict[str, Any]:
    game = config["project"]["game"]
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    manifest: dict[str, Any] = {"game": game, "run_id": run_id, "sources": {}, "total_records": 0}
    all_rows: list[dict[str, Any]] = []
    for source, collector in COLLECTORS.items():
        source_config = config.get("sources", {}).get(source, {})
        if selected and source not in selected:
            continue
        if not source_config.get("enabled", False):
            manifest["sources"][source] = {
                "status": "disabled", "records": 0, "queries_attempted": 0,
                "items_retrieved": 0, "excluded": {},
            }
            continue
        try:
            if source in ADAPTER_RESULT_COLLECTORS:
                result = ADAPTER_RESULT_COLLECTORS[source](game, source_config, run_id=f"run_{run_id}")
                if result.status in {SourceStatus.UNAVAILABLE, SourceStatus.FAILED}:
                    manifest["sources"][source] = {
                        **result.manifest_status(),
                        "records": 0,
                    }
                    if strict:
                        raise CollectionError(result.reason or f"{source} unavailable")
                    continue
                rows = [evidence_to_legacy_row(item, game_title=game) for item in result.items]
            else:
                result = None
                rows = collector(game, source_config)
            snapshot = root / "data/raw" / source / f"{run_id}.jsonl"
            save_raw_snapshot(rows, snapshot)
            all_rows.extend(rows)
            if result is not None:
                manifest["sources"][source] = {
                    **result.manifest_status(),
                    "records": len(rows),
                    "snapshot": str(snapshot.relative_to(root)),
                }
            else:
                manifest["sources"][source] = {
                    "status": "collected", "records": len(rows), "items_retrieved": len(rows),
                    "queries_attempted": 1, "excluded": {},
                    "snapshot": str(snapshot.relative_to(root)),
                }
        except (CollectionError, ValueError, KeyError) as exc:
            manifest["sources"][source] = {
                "status": "unavailable", "records": 0, "items_retrieved": 0,
                "queries_attempted": 1, "excluded": {}, "reason": str(exc),
            }
            if strict:
                raise
    processed = root / "data/processed/voice.csv"
    if all_rows and replace_game:
        incoming, duplicates = replace_game_csv(all_rows, processed, game)
    else:
        incoming, duplicates = upsert_csv(all_rows, processed) if all_rows else (0, 0)
    manifest["total_records"] = incoming
    manifest["duplicates_replaced"] = duplicates
    manifest["replace_game"] = replace_game
    manifest["dataset"] = str(processed.relative_to(root))
    manifest_path = root / "data/raw" / f"manifest_{run_id}.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    latest = root / "data/raw/latest_manifest.json"
    latest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
