"""Capability-only descriptors for platforms without a permitted live route."""

from __future__ import annotations

from typing import Any

from ...models import EvidenceItem, QueryPlan
from ..base import (
    AuthModel,
    BaseSourceAdapter,
    PaginationModel,
    QueryStyle,
    RetrievalContext,
    SourceCapabilities,
    SourcePage,
    SourceUnavailableError,
)


class RestrictedPlatformAdapter(BaseSourceAdapter):
    def __init__(self, name: str, *, evidence_kinds: list[str], notes: str) -> None:
        self.name = name
        self._evidence_kinds = evidence_kinds
        self._notes = notes

    def capabilities(self) -> SourceCapabilities:
        return SourceCapabilities(
            source=self.name,
            evidence_kinds=list(self._evidence_kinds),
            auth_model=AuthModel.RESTRICTED,
            pagination=PaginationModel.NONE,
            supported_query_styles=[QueryStyle.TEXT_SEARCH],
            languages=["*"],
            supported_intents=["*"],
            rate_limit={},
            live_retrieval=False,
            availability_notes=self._notes,
        )

    def search(self, plan: QueryPlan, cursor: str | None = None) -> SourcePage:
        raise SourceUnavailableError(
            f"{self.name} has no permitted public collector; configure an authorised export or licensed provider",
            error_code="restricted_platform",
        )

    def normalize(self, native_item: dict[str, Any], context: RetrievalContext) -> EvidenceItem:
        raise NotImplementedError("Restricted capability stubs never receive native items")


def restricted_adapter_registry() -> dict[str, RestrictedPlatformAdapter]:
    common = "Capability descriptor only; it performs no network request."
    return {
        "taptap": RestrictedPlatformAdapter("taptap", evidence_kinds=["review", "post"], notes=common),
        "weibo": RestrictedPlatformAdapter("weibo", evidence_kinds=["post", "comment"], notes=common),
        "xiaohongshu": RestrictedPlatformAdapter("xiaohongshu", evidence_kinds=["post", "comment"], notes=common),
        "douyin": RestrictedPlatformAdapter("douyin", evidence_kinds=["video", "comment"], notes=common),
        "app_store": RestrictedPlatformAdapter("app_store", evidence_kinds=["review"], notes=common),
        "google_play": RestrictedPlatformAdapter("google_play", evidence_kinds=["review"], notes=common),
    }
