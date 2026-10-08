from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from typing import Any

from ..http import CollectionError, request_json
from ..models import EvidenceItem, QueryPlan
from .base import (
    ADAPTER_CONTRACT_VERSION,
    AdapterRunResult,
    AuthModel,
    BaseSourceAdapter,
    ExcludedContent,
    PaginationModel,
    QueryStyle,
    RetrievalContext,
    SourceCapabilities,
    SourcePage,
    SourceStatus,
    SourceUnavailableError,
    collect_all_pages,
    evidence_to_legacy_row,
    make_provenance,
    stable_evidence_id,
    stable_game_id,
)


ENDPOINT = "https://store.steampowered.com/appreviews/{app_id}"


class SteamReviewsAdapter(BaseSourceAdapter):
    """Steam's public app-review endpoint behind the shared adapter contract."""

    name = "steam"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = dict(config or {})

    def capabilities(self) -> SourceCapabilities:
        return SourceCapabilities(
            source=self.name,
            evidence_kinds=["review"],
            auth_model=AuthModel.NONE,
            pagination=PaginationModel.CURSOR,
            supported_query_styles=[QueryStyle.ENTITY_ID],
            languages=["all", "en", "zh-CN"],
            supported_intents=["*"],
            rate_limit={
                "request_delay_seconds": float(self.config.get("request_delay_seconds", 0.35)),
                "retries": int(self.config.get("retries", 3)),
                "max_page_size": 100,
            },
            live_retrieval=True,
            availability_notes="Public Steam app review endpoint; requires a canonical app ID.",
        )

    def _app_id(self, plan: QueryPlan) -> int:
        configured = self.config.get("app_id")
        if configured is not None:
            return int(configured)
        match = re.search(r"steam_app:(\d+)", plan.query_text)
        if match:
            return int(match.group(1))
        raise SourceUnavailableError(
            "Steam collection requires a canonical steam_app_id",
            error_code="missing_entity_id",
        )

    @staticmethod
    def _decode_cursor(cursor: str | None) -> tuple[str, int]:
        if cursor is None:
            return "*", 0
        try:
            payload = json.loads(cursor)
            return str(payload["source_cursor"]), int(payload["offset"])
        except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
            raise SourceUnavailableError("Invalid Steam cursor state", error_code="invalid_cursor") from exc

    def search(self, plan: QueryPlan, cursor: str | None = None) -> SourcePage:
        app_id = self._app_id(plan)
        source_cursor, offset = self._decode_cursor(cursor)
        limit = int(self.config.get("limit", self.config.get("limit_per_app", 500)))
        page_size = min(100, max(1, limit - offset))
        if cursor is not None:
            time.sleep(float(self.config.get("request_delay_seconds", 0.35)))
        payload = request_json(
            ENDPOINT.format(app_id=app_id),
            params={
                "json": 1,
                "filter": self.config.get("filter", "recent"),
                "language": self.config.get("language", "english"),
                "review_type": self.config.get("review_type", "all"),
                "purchase_type": self.config.get("purchase_type", "all"),
                "num_per_page": page_size,
                "cursor": source_cursor,
            },
            headers={"User-Agent": self.config.get("user_agent", "PlayerVoice/0.3")},
            retries=int(self.config.get("retries", 3)),
            timeout=int(self.config.get("timeout", 30)),
        )
        reviews = payload.get("reviews") or []
        if not isinstance(reviews, list):
            raise SourceUnavailableError("Steam response did not contain a review list", error_code="invalid_response")
        next_source_cursor = payload.get("cursor")
        next_offset = offset + len(reviews)
        next_cursor = None
        if reviews and next_source_cursor and next_source_cursor != source_cursor and next_offset < limit:
            next_cursor = json.dumps(
                {"offset": next_offset, "source_cursor": str(next_source_cursor)},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        native_items = [dict(review, _adapter_app_id=app_id) for review in reviews if isinstance(review, dict)]
        return SourcePage(
            source=self.name,
            status=SourceStatus.COLLECTED,
            cursor=cursor,
            next_cursor=next_cursor,
            native_items=native_items,
            requests_made=1,
        )

    def normalize(self, native_item: dict[str, Any], context: RetrievalContext) -> EvidenceItem:
        text = " ".join(str(native_item.get("review") or "").split())
        if not text or text.casefold() in {"[deleted]", "[removed]"}:
            raise ExcludedContent("empty_or_deleted")
        recommendation_id = native_item.get("recommendationid")
        if recommendation_id is None:
            raise ExcludedContent("missing_source_id")
        app_id = int(native_item["_adapter_app_id"])
        author = native_item.get("author") if isinstance(native_item.get("author"), dict) else {}
        author_id = str(author.get("steamid") or "")
        anonymised_author_id = (
            hashlib.sha256(f"steam:{author_id}".encode("utf-8")).hexdigest()[:16]
            if author_id
            else None
        )
        timestamp = native_item.get("timestamp_created")
        published_at = (
            datetime.fromtimestamp(int(timestamp), tz=timezone.utc) if timestamp is not None else None
        )
        metadata = {
            "app_id": app_id,
            "app_name": self.config.get("app_name"),
            "role": self.config.get("role", "focal"),
            "steam_purchase": bool(native_item.get("steam_purchase")),
            "received_for_free": bool(native_item.get("received_for_free")),
            "votes_funny": int(native_item.get("votes_funny") or 0),
            "anonymised_author_id": anonymised_author_id,
            "query_provenance": context.query_provenance,
        }
        return EvidenceItem(
            evidence_id=stable_evidence_id(self.name, str(recommendation_id)),
            game_id=context.game_id,
            evidence_kind="review",
            access_scope="public",
            dataset_id=None,
            source=self.name,
            source_content_id=str(recommendation_id),
            source_url=f"https://steamcommunity.com/app/{app_id}/reviews/",
            source_reference=f"steam:app:{app_id}:review:{recommendation_id}",
            title=None,
            original_text=text,
            normalized_text=None,
            language=context.query_plan.language,
            published_at=published_at,
            retrieved_at=context.retrieved_at,
            run_id=context.run_id,
            query_id=context.query_plan.query_id,
            matched_alias_ids=list(context.query_plan.alias_ids),
            retrieval_method="public_endpoint",
            relevance_label="pending",
            relevance_score=None,
            relevance_reasons=["retrieved by source adapter; relevance not yet evaluated"],
            relevance_method_version=None,
            recommended=bool(native_item.get("voted_up")),
            rating=None,
            rating_scale=None,
            engagement={"helpful_votes": int(native_item.get("votes_up") or 0)},
            reply_count=int(native_item.get("comment_count") or 0),
            playtime_hours=round(float(author.get("playtime_forever") or 0) / 60, 1),
            platform="steam",
            source_metadata=metadata,
            provenance=make_provenance(
                source_class="platform_store",
                collector_version=ADAPTER_CONTRACT_VERSION,
                text=text,
                raw_snapshot_reference=context.raw_snapshot_reference,
                terms_or_permission_reference="Steam public appreviews endpoint",
            ),
        )


def _legacy_plan(game: str, app_id: int, run_id: str, language: str) -> QueryPlan:
    query_text = f"steam_app:{app_id} intent:general"
    digest = hashlib.sha256(f"{run_id}|steam|{query_text}".encode("utf-8")).hexdigest()[:20]
    return QueryPlan(
        query_id=f"query_{digest}",
        run_id=run_id,
        game_id=stable_game_id(game),
        source="steam",
        language=language,
        intent="general",
        query_text=query_text,
        alias_ids=[],
        disambiguators=[],
        expected_evidence_kind="review",
        generated_at=datetime.now(timezone.utc),
    )


def collect_steam_result(game: str, config: dict[str, Any], *, run_id: str) -> AdapterRunResult:
    combined_items: list[EvidenceItem] = []
    combined_exclusions: dict[str, int] = {}
    cursors: list[str] = []
    requests = 0
    pages = 0
    statuses: list[SourceStatus] = []
    reasons: list[str] = []
    apps = config.get("apps") or ([config] if config.get("app_id") else [])
    if not apps:
        return AdapterRunResult(
            source="steam",
            status=SourceStatus.UNAVAILABLE,
            items=[],
            queries_attempted=0,
            requests_made=0,
            pages_retrieved=0,
            excluded_counts={},
            cursors=[],
            error_code="missing_entity_id",
            reason="Steam collection requires at least one app_id",
        )
    for app in apps:
        app_config = {**config, **app, "limit": int(app.get("limit", config.get("limit_per_app", 500)))}
        app_id = int(app["app_id"])
        plan = _legacy_plan(game, app_id, run_id, str(config.get("language", "en")))
        context = RetrievalContext(
            original_game_input=game,
            game_id=plan.game_id,
            canonical_title=game,
            run_id=run_id,
            query_plan=plan,
        )
        result = collect_all_pages(SteamReviewsAdapter(app_config), plan, context)
        combined_items.extend(result.items)
        requests += result.requests_made
        pages += result.pages_retrieved
        cursors.extend(result.cursors)
        statuses.append(result.status)
        if result.reason:
            reasons.append(result.reason)
        for key, value in result.excluded_counts.items():
            combined_exclusions[key] = combined_exclusions.get(key, 0) + value
    status = SourceStatus.COLLECTED
    if any(value in {SourceStatus.UNAVAILABLE, SourceStatus.FAILED, SourceStatus.PARTIAL} for value in statuses):
        status = SourceStatus.PARTIAL if combined_items else statuses[0]
    return AdapterRunResult(
        source="steam",
        status=status,
        items=combined_items,
        queries_attempted=len(apps),
        requests_made=requests,
        pages_retrieved=pages,
        excluded_counts=combined_exclusions,
        cursors=cursors,
        error_code=None if status == SourceStatus.COLLECTED else "partial_collection",
        reason="; ".join(reasons) or None,
    )


def collect_steam(game: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    """Backward-compatible legacy row wrapper over :class:`SteamReviewsAdapter`."""

    run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    result = collect_steam_result(game, config, run_id=run_id)
    if result.status in {SourceStatus.UNAVAILABLE, SourceStatus.FAILED}:
        raise CollectionError(result.reason or "Steam is unavailable")
    rows = [evidence_to_legacy_row(item, game_title=game) for item in result.items]
    if not rows:
        raise CollectionError("Steam returned no reviews for the configured apps")
    return rows
