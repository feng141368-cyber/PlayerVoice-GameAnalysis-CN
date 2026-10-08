from __future__ import annotations

import hashlib
import html
import json
import re
import time
from datetime import datetime, timezone
from math import ceil
from typing import Any

from ..http import request_json
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


SEARCH_API = "https://api.bilibili.com/x/web-interface/search/type"
REPLY_API = "https://api.bilibili.com/x/v2/reply"


def _plain(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value or "")).strip()


class BilibiliCommentsAdapter(BaseSourceAdapter):
    """Bilibili public video-search/comment endpoints with resumable state."""

    name = "bilibili"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = dict(config or {})

    def capabilities(self) -> SourceCapabilities:
        return SourceCapabilities(
            source=self.name,
            evidence_kinds=["comment"],
            auth_model=AuthModel.NONE,
            pagination=PaginationModel.COMPOSITE_CURSOR,
            supported_query_styles=[QueryStyle.TEXT_SEARCH],
            languages=["zh-CN"],
            supported_intents=["*"],
            rate_limit={
                "request_delay_seconds": float(self.config.get("request_delay_seconds", 0.6)),
                "retries": int(self.config.get("retries", 3)),
                "search_page_size_max": 50,
                "comment_page_size_max": 20,
            },
            live_retrieval=True,
            availability_notes="Public endpoints may be regionally unavailable or rate limited.",
        )

    @staticmethod
    def _decode_cursor(cursor: str | None) -> tuple[int, int, int]:
        if cursor is None:
            return 1, 0, 1
        try:
            payload = json.loads(cursor)
            return int(payload["search_page"]), int(payload["video_index"]), int(payload["comment_page"])
        except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
            raise SourceUnavailableError("Invalid Bilibili cursor state", error_code="invalid_cursor") from exc

    @staticmethod
    def _cursor(search_page: int, video_index: int, comment_page: int) -> str:
        return json.dumps(
            {
                "comment_page": comment_page,
                "search_page": search_page,
                "video_index": video_index,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    def search(self, plan: QueryPlan, cursor: str | None = None) -> SourcePage:
        search_page, video_index, comment_page = self._decode_cursor(cursor)
        max_search_pages = int(self.config.get("search_pages", 1))
        videos_per_page = min(int(self.config.get("videos_per_page", 20)), 50)
        max_videos = int(self.config.get("max_videos", 10))
        comments_per_video = int(self.config.get("comments_per_video", 50))
        global_video_index = (search_page - 1) * videos_per_page + video_index
        if search_page > max_search_pages or global_video_index >= max_videos:
            return SourcePage(source=self.name, status=SourceStatus.COLLECTED, cursor=cursor)
        if cursor is not None:
            time.sleep(float(self.config.get("request_delay_seconds", 0.6)))
        headers = {
            "User-Agent": self.config.get("user_agent", "Mozilla/5.0 PlayerVoice/0.3"),
            "Referer": "https://search.bilibili.com/",
        }
        search_payload = request_json(
            SEARCH_API,
            params={
                "search_type": "video",
                "keyword": self.config.get("query") or plan.query_text,
                "page": search_page,
                "page_size": videos_per_page,
            },
            headers=headers,
            retries=int(self.config.get("retries", 3)),
            timeout=int(self.config.get("timeout", 30)),
        )
        if search_payload.get("code") != 0:
            raise SourceUnavailableError(
                f"Bilibili search unavailable: {search_payload.get('message')}",
                error_code=f"bilibili_{search_payload.get('code')}",
            )
        videos = (search_payload.get("data") or {}).get("result") or []
        if not isinstance(videos, list):
            raise SourceUnavailableError("Bilibili search response was invalid", error_code="invalid_response")
        if video_index >= len(videos):
            next_cursor = None
            if videos and search_page < max_search_pages:
                next_cursor = self._cursor(search_page + 1, 0, 1)
            return SourcePage(
                source=self.name,
                status=SourceStatus.COLLECTED,
                cursor=cursor,
                next_cursor=next_cursor,
                requests_made=1,
            )
        video = videos[video_index]
        aid, bvid = video.get("aid"), video.get("bvid")
        next_video = self._cursor(search_page, video_index + 1, 1)
        if not aid or not bvid:
            return SourcePage(
                source=self.name,
                status=SourceStatus.COLLECTED,
                cursor=cursor,
                next_cursor=next_video,
                requests_made=1,
                excluded_counts={"missing_video_id": 1},
            )
        page_size = min(20, max(1, comments_per_video - ((comment_page - 1) * 20)))
        response = request_json(
            REPLY_API,
            params={"type": 1, "oid": aid, "pn": comment_page, "ps": page_size, "sort": 2},
            headers={**headers, "Referer": f"https://www.bilibili.com/video/{bvid}/"},
            retries=int(self.config.get("retries", 3)),
            timeout=int(self.config.get("timeout", 30)),
        )
        if response.get("code") != 0:
            raise SourceUnavailableError(
                f"Bilibili comments unavailable for {bvid}: {response.get('message')}",
                error_code=f"bilibili_{response.get('code')}",
            )
        replies = (response.get("data") or {}).get("replies") or []
        if not isinstance(replies, list):
            raise SourceUnavailableError("Bilibili reply response was invalid", error_code="invalid_response")
        max_comment_pages = max(1, ceil(comments_per_video / 20))
        if replies and len(replies) >= page_size and comment_page < max_comment_pages:
            next_cursor = self._cursor(search_page, video_index, comment_page + 1)
        elif video_index + 1 < len(videos) and global_video_index + 1 < max_videos:
            next_cursor = next_video
        elif search_page < max_search_pages and global_video_index + 1 < max_videos:
            next_cursor = self._cursor(search_page + 1, 0, 1)
        else:
            next_cursor = None
        enriched = [
            dict(reply, _adapter_video={"aid": aid, "bvid": bvid, "title": _plain(video.get("title", ""))})
            for reply in replies
            if isinstance(reply, dict)
        ]
        return SourcePage(
            source=self.name,
            status=SourceStatus.COLLECTED,
            cursor=cursor,
            next_cursor=next_cursor,
            native_items=enriched,
            requests_made=2,
        )

    def normalize(self, native_item: dict[str, Any], context: RetrievalContext) -> EvidenceItem:
        text = _plain(str((native_item.get("content") or {}).get("message", "")))
        if not text or text.casefold() in {"[deleted]", "[removed]"}:
            raise ExcludedContent("empty_or_deleted")
        reply_id = native_item.get("rpid_str") or native_item.get("rpid")
        if not reply_id:
            raise ExcludedContent("missing_source_id")
        video = native_item.get("_adapter_video") or {}
        bvid = str(video.get("bvid") or "")
        if not bvid:
            raise ExcludedContent("missing_video_id")
        member = native_item.get("member") if isinstance(native_item.get("member"), dict) else {}
        member_id = str(member.get("mid") or "")
        anonymised_author_id = (
            hashlib.sha256(f"bilibili:{member_id}".encode("utf-8")).hexdigest()[:16]
            if member_id
            else None
        )
        timestamp = int(native_item.get("ctime") or 0)
        published_at = datetime.fromtimestamp(timestamp, tz=timezone.utc) if timestamp > 0 else None
        parent_id = native_item.get("parent") or native_item.get("root")
        metadata = {
            "aid": video.get("aid"),
            "bvid": bvid,
            "video_title": video.get("title"),
            "anonymised_author_id": anonymised_author_id,
            "query_provenance": context.query_provenance,
        }
        return EvidenceItem(
            evidence_id=stable_evidence_id(self.name, str(reply_id)),
            game_id=context.game_id,
            evidence_kind="comment",
            access_scope="public",
            dataset_id=None,
            source=self.name,
            source_content_id=str(reply_id),
            parent_evidence_id=stable_evidence_id(self.name, str(parent_id)) if parent_id else None,
            source_url=f"https://www.bilibili.com/video/{bvid}/#reply{reply_id}",
            source_reference=f"bilibili:{bvid}:reply:{reply_id}",
            title=video.get("title") or None,
            original_text=text,
            normalized_text=None,
            language="zh-CN",
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
            recommended=None,
            rating=None,
            rating_scale=None,
            engagement={
                "likes": int(native_item.get("like") or 0),
                "replies": int(native_item.get("rcount") or 0),
            },
            reply_count=int(native_item.get("rcount") or 0),
            playtime_hours=None,
            platform="bilibili",
            source_metadata=metadata,
            provenance=make_provenance(
                source_class="public_community",
                collector_version=ADAPTER_CONTRACT_VERSION,
                text=text,
                raw_snapshot_reference=context.raw_snapshot_reference,
                terms_or_permission_reference="Bilibili public web endpoints",
            ),
        )


def _legacy_plan(game: str, query: str, run_id: str) -> QueryPlan:
    digest = hashlib.sha256(f"{run_id}|bilibili|{query}".encode("utf-8")).hexdigest()[:20]
    return QueryPlan(
        query_id=f"query_{digest}",
        run_id=run_id,
        game_id=stable_game_id(game),
        source="bilibili",
        language="zh-CN",
        intent="general",
        query_text=query,
        alias_ids=[],
        disambiguators=[],
        expected_evidence_kind="comment",
        generated_at=datetime.now(timezone.utc),
    )


def collect_bilibili_result(game: str, config: dict[str, Any], *, run_id: str) -> AdapterRunResult:
    query = str(config.get("query") or game)
    plan = _legacy_plan(game, query, run_id)
    context = RetrievalContext(
        original_game_input=game,
        game_id=plan.game_id,
        canonical_title=game,
        run_id=run_id,
        query_plan=plan,
    )
    return collect_all_pages(BilibiliCommentsAdapter(config), plan, context)


def collect_bilibili(game: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    """Backward-compatible legacy row wrapper over :class:`BilibiliCommentsAdapter`."""

    run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    result = collect_bilibili_result(game, config, run_id=run_id)
    return [evidence_to_legacy_row(item, game_title=game) for item in result.items]
