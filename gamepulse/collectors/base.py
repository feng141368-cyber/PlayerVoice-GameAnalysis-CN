"""Typed contracts and shared orchestration for community source adapters.

Adapters own source-specific retrieval and normalization only.  They do not
score relevance, classify topics, or render product modes.
"""

from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import AwareDatetime, Field

from ..http import CollectionError
from ..models import ContractModel, EvidenceItem, Provenance, QueryPlan
from ..schema import record


ADAPTER_CONTRACT_VERSION = "source-adapter-v1"


class SourceStatus(str, Enum):
    COLLECTED = "collected"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class AuthModel(str, Enum):
    NONE = "none"
    OAUTH_CLIENT_CREDENTIALS = "oauth_client_credentials"
    API_KEY = "api_key"
    LICENSED_PROVIDER = "licensed_provider"
    AUTHORISED_EXPORT = "authorised_export"
    RESTRICTED = "restricted"


class PaginationModel(str, Enum):
    NONE = "none"
    CURSOR = "cursor"
    PAGE = "page"
    COMPOSITE_CURSOR = "composite_cursor"


class QueryStyle(str, Enum):
    ENTITY_ID = "entity_id"
    TEXT_SEARCH = "text_search"
    CHANNEL_SEARCH = "channel_search"
    DIRECT_URL = "direct_url"


class SourceCapabilities(ContractModel):
    source: str = Field(min_length=1)
    evidence_kinds: list[str]
    auth_model: AuthModel
    pagination: PaginationModel
    supported_query_styles: list[QueryStyle]
    languages: list[str]
    supported_intents: list[str]
    rate_limit: dict[str, Any]
    live_retrieval: bool
    availability_notes: str | None = None


class RetrievalContext(ContractModel):
    original_game_input: str = Field(min_length=1)
    game_id: str = Field(pattern=r"^game_.+")
    canonical_title: str = Field(min_length=1)
    run_id: str = Field(pattern=r"^run_.+")
    query_plan: QueryPlan
    retrieved_at: AwareDatetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw_snapshot_reference: str | None = None

    @property
    def query_provenance(self) -> dict[str, Any]:
        plan = self.query_plan
        return {
            "original_game_input": self.original_game_input,
            "canonical_game_id": self.game_id,
            "query_id": plan.query_id,
            "query_intent": plan.intent.value,
            "language": plan.language,
            "platform": plan.source,
            "alias_ids": list(plan.alias_ids),
            "actual_query": plan.query_text,
            "source": plan.source,
            "retrieved_at": self.retrieved_at.isoformat(),
        }


class SourcePage(ContractModel):
    source: str = Field(min_length=1)
    status: SourceStatus
    cursor: str | None = None
    next_cursor: str | None = None
    native_items: list[dict[str, Any]] = Field(default_factory=list)
    evidence_items: list[EvidenceItem] = Field(default_factory=list)
    requests_made: int = Field(default=0, ge=0)
    excluded_counts: dict[str, int] = Field(default_factory=dict)
    error_code: str | None = None
    reason: str | None = None


class AdapterRunResult(ContractModel):
    source: str
    status: SourceStatus
    items: list[EvidenceItem]
    queries_attempted: int = Field(ge=0)
    requests_made: int = Field(ge=0)
    pages_retrieved: int = Field(ge=0)
    excluded_counts: dict[str, int]
    cursors: list[str]
    error_code: str | None = None
    reason: str | None = None

    def manifest_status(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "queries_attempted": self.queries_attempted,
            "requests_made": self.requests_made,
            "items_retrieved": len(self.items),
            "excluded": dict(self.excluded_counts),
            "error_code": self.error_code,
            "reason": self.reason,
        }


class SourceUnavailableError(RuntimeError):
    """The configured source cannot be queried safely in this environment."""

    def __init__(self, reason: str, *, error_code: str = "source_unavailable") -> None:
        super().__init__(reason)
        self.error_code = error_code


class ExcludedContent(ValueError):
    """A native record was retrieved but must not enter normalized evidence."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@runtime_checkable
class SourceAdapter(Protocol):
    name: str

    def capabilities(self) -> SourceCapabilities: ...

    def search(self, plan: QueryPlan, cursor: str | None = None) -> SourcePage: ...

    def normalize(self, native_item: dict[str, Any], context: RetrievalContext) -> EvidenceItem: ...


class BaseSourceAdapter(ABC):
    name: str

    @abstractmethod
    def capabilities(self) -> SourceCapabilities:
        raise NotImplementedError

    @abstractmethod
    def search(self, plan: QueryPlan, cursor: str | None = None) -> SourcePage:
        raise NotImplementedError

    @abstractmethod
    def normalize(self, native_item: dict[str, Any], context: RetrievalContext) -> EvidenceItem:
        raise NotImplementedError

    def retrieve_page(
        self,
        plan: QueryPlan,
        context: RetrievalContext,
        cursor: str | None = None,
    ) -> SourcePage:
        try:
            page = self.search(plan, cursor)
        except SourceUnavailableError as exc:
            return SourcePage(
                source=self.name,
                status=SourceStatus.UNAVAILABLE,
                cursor=cursor,
                error_code=exc.error_code,
                reason=str(exc),
            )
        except CollectionError as exc:
            return SourcePage(
                source=self.name,
                status=SourceStatus.UNAVAILABLE,
                cursor=cursor,
                error_code="collection_error",
                reason=str(exc),
            )

        normalized: list[EvidenceItem] = []
        exclusions = dict(page.excluded_counts)
        for native_item in page.native_items:
            try:
                normalized.append(self.normalize(native_item, context))
            except ExcludedContent as exc:
                exclusions[exc.reason] = exclusions.get(exc.reason, 0) + 1
        return page.model_copy(update={"evidence_items": normalized, "excluded_counts": exclusions})


def collect_all_pages(
    adapter: BaseSourceAdapter,
    plan: QueryPlan,
    context: RetrievalContext,
    *,
    max_pages: int = 100,
) -> AdapterRunResult:
    """Execute one plan with bounded, cycle-safe source pagination."""

    items: list[EvidenceItem] = []
    exclusions: dict[str, int] = {}
    cursor: str | None = None
    seen_cursors: set[str] = set()
    cursor_history: list[str] = []
    requests_made = 0
    pages = 0
    status = SourceStatus.COLLECTED
    error_code: str | None = None
    reason: str | None = None

    while pages < max_pages:
        cursor_key = cursor if cursor is not None else "<initial>"
        if cursor_key in seen_cursors:
            status = SourceStatus.PARTIAL if items else SourceStatus.FAILED
            error_code = "cursor_cycle"
            reason = f"adapter repeated cursor {cursor_key!r}"
            break
        seen_cursors.add(cursor_key)
        cursor_history.append(cursor_key)
        page = adapter.retrieve_page(plan, context, cursor)
        requests_made += page.requests_made
        if page.status == SourceStatus.UNAVAILABLE:
            status = SourceStatus.PARTIAL if items else SourceStatus.UNAVAILABLE
            error_code = page.error_code
            reason = page.reason
            break
        if page.status == SourceStatus.FAILED:
            status = SourceStatus.PARTIAL if items else SourceStatus.FAILED
            error_code = page.error_code
            reason = page.reason
            break
        pages += 1
        items.extend(page.evidence_items)
        for key, value in page.excluded_counts.items():
            exclusions[key] = exclusions.get(key, 0) + value
        if not page.next_cursor:
            break
        cursor = page.next_cursor
    else:
        status = SourceStatus.PARTIAL
        error_code = "page_limit"
        reason = f"adapter exceeded the bounded page limit ({max_pages})"

    return AdapterRunResult(
        source=adapter.name,
        status=status,
        items=items,
        queries_attempted=1,
        requests_made=requests_made,
        pages_retrieved=pages,
        excluded_counts=exclusions,
        cursors=cursor_history,
        error_code=error_code,
        reason=reason,
    )


def stable_game_id(title: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-") or "unknown"
    digest = hashlib.sha256(title.casefold().encode("utf-8")).hexdigest()[:8]
    return f"game_{normalized[:48]}_{digest}"


def stable_evidence_id(source: str, source_content_id: str) -> str:
    digest = hashlib.sha256(f"{source}:{source_content_id}".encode("utf-8")).hexdigest()[:20]
    return f"ev_{digest}"


def content_checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def evidence_to_legacy_row(item: EvidenceItem, *, game_title: str) -> dict[str, Any]:
    """Preserve the pre-contract CSV output while collection migrates by adapter."""

    metadata = dict(item.source_metadata)
    return record(
        source=item.source,
        source_type="store_review" if item.source == "steam" else "video_comment",
        game=game_title,
        channel=str(metadata.get("app_id") or metadata.get("bvid") or item.source),
        content_type=item.evidence_kind.value,
        source_content_id=item.source_content_id,
        parent_id=item.parent_evidence_id.removeprefix("ev_") if item.parent_evidence_id else None,
        created_at=item.published_at.isoformat() if item.published_at else item.retrieved_at.isoformat(),
        collected_at=item.retrieved_at.isoformat(),
        title=item.title,
        text=item.original_text,
        url=item.source_url,
        language=item.language,
        recommended=item.recommended,
        rating=item.rating,
        engagement_score=(
            item.engagement or 0
            if isinstance(item.engagement, (int, float))
            else (item.engagement or {}).get("helpful_votes", (item.engagement or {}).get("likes", 0))
        ),
        reply_count=item.reply_count,
        playtime_hours=item.playtime_hours,
        metadata_json=metadata,
    )


def make_provenance(
    *,
    source_class: str,
    collector_version: str,
    text: str,
    raw_snapshot_reference: str | None,
    terms_or_permission_reference: str | None,
) -> Provenance:
    return Provenance(
        source_class=source_class,
        collector_version=collector_version,
        terms_or_permission_reference=terms_or_permission_reference,
        content_checksum=content_checksum(text),
        raw_snapshot_reference=raw_snapshot_reference,
        contains_personal_data=False,
        redaction_status="not_required",
    )
