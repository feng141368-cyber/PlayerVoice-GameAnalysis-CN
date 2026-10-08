"""Compatibility mappings from the pre-contract normalized voice schema."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any, Mapping

from .models import EvidenceItem, Provenance


def _none_if_missing(value: Any) -> Any:
    if value is None:
        return None
    try:
        if math.isnan(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if text.casefold() in {"", "nan", "none", "null", "<na>"}:
        return None
    return value


def _optional_str(value: Any) -> str | None:
    value = _none_if_missing(value)
    return None if value is None else str(value)


def _optional_float(value: Any) -> float | None:
    value = _none_if_missing(value)
    return None if value is None else float(value)


def _optional_int(value: Any) -> int | None:
    value = _none_if_missing(value)
    return None if value is None else int(float(value))


def _optional_bool(value: Any) -> bool | None:
    value = _none_if_missing(value)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().casefold()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ValueError(f"Cannot interpret recommended value as boolean: {value!r}")


def _metadata(value: Any) -> dict[str, Any]:
    value = _none_if_missing(value)
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    parsed = json.loads(str(value))
    if not isinstance(parsed, dict):
        raise ValueError("legacy metadata_json must contain a JSON object")
    return parsed


def _stable_game_id(title: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-") or "unknown"
    digest = hashlib.sha256(title.casefold().encode("utf-8")).hexdigest()[:8]
    return f"game_{normalized[:48]}_{digest}"


def _evidence_kind(content_type: str | None, source_type: str | None) -> str:
    for candidate in (content_type, source_type):
        normalized = (candidate or "").casefold()
        if "review" in normalized:
            return "review"
        if "comment" in normalized:
            return "comment"
        if "post" in normalized:
            return "post"
        if "video" in normalized:
            return "video"
    return "post"


def normalized_voice_row_to_evidence(
    row: Mapping[str, Any],
    *,
    game_id: str | None = None,
    run_id: str = "run_legacy_voice_import",
) -> EvidenceItem:
    """Convert one legacy normalized row without changing its source semantics."""

    source = str(row["source"])
    source_content_id = str(row["source_content_id"])
    original_text = str(row["text"])
    game_title = str(row["game"])
    record_id = str(row["record_id"])
    source_type = _optional_str(row.get("source_type"))
    content_type = _optional_str(row.get("content_type"))
    source_url = _optional_str(row.get("url"))
    channel = _optional_str(row.get("channel"))
    source_reference = None if source_url else f"{source}:{channel or source_content_id}"
    metadata = _metadata(row.get("metadata_json"))
    metadata.update(
        {
            "legacy_record_id": record_id,
            "legacy_game_title": game_title,
            "legacy_source_type": source_type,
            "legacy_content_type": content_type,
            "legacy_channel": channel,
        }
    )
    parent_id = _optional_str(row.get("parent_id"))
    engagement_score = _optional_float(row.get("engagement_score"))
    checksum = hashlib.sha256(original_text.encode("utf-8")).hexdigest()
    source_class = "platform_store" if source == "steam" else "public_community"
    retrieval_method = "licensed_provider" if source_type == "licensed_provider" else "public_endpoint"

    return EvidenceItem(
        evidence_id=f"ev_{record_id}",
        game_id=game_id or _stable_game_id(game_title),
        evidence_kind=_evidence_kind(content_type, source_type),
        access_scope="public",
        dataset_id=None,
        source=source,
        source_content_id=source_content_id,
        parent_evidence_id=f"ev_{parent_id}" if parent_id else None,
        source_url=source_url,
        source_reference=source_reference,
        title=_optional_str(row.get("title")),
        original_text=original_text,
        normalized_text=None,
        language=_optional_str(row.get("language")),
        published_at=_optional_str(row.get("created_at")),
        retrieved_at=_optional_str(row.get("collected_at")) or datetime.now(timezone.utc),
        run_id=run_id,
        query_id=None,
        matched_alias_ids=[],
        retrieval_method=retrieval_method,
        relevance_label="pending",
        relevance_score=None,
        relevance_reasons=["legacy normalized row; relevance not yet evaluated"],
        relevance_method_version=None,
        recommended=_optional_bool(row.get("recommended")),
        rating=_optional_float(row.get("rating")),
        rating_scale=None,
        engagement=engagement_score,
        reply_count=_optional_int(row.get("reply_count")),
        playtime_hours=_optional_float(row.get("playtime_hours")),
        platform=source,
        source_metadata=metadata,
        provenance=Provenance(
            source_class=source_class,
            collector_version="legacy-normalized-row-v1",
            terms_or_permission_reference=None,
            content_checksum=checksum,
            raw_snapshot_reference=None,
            contains_personal_data=False,
            redaction_status="not_required",
        ),
    )
