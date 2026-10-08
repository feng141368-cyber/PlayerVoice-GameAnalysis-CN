"""Official-source adapter boundary.

Issue 5's Fact Layer remains the only implementation that emits official
facts.  This boundary lets source orchestration report that separation without
inventing a generic web scraper.
"""

from __future__ import annotations

from typing import Any

from ..models import EvidenceItem, QueryPlan
from .base import (
    AuthModel,
    BaseSourceAdapter,
    PaginationModel,
    QueryStyle,
    RetrievalContext,
    SourceCapabilities,
    SourcePage,
    SourceUnavailableError,
)


class OfficialSourceAdapter(BaseSourceAdapter):
    name = "official"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = dict(config or {})

    def capabilities(self) -> SourceCapabilities:
        return SourceCapabilities(
            source=self.name,
            evidence_kinds=["official", "fact_source", "patch_note"],
            auth_model=AuthModel.NONE,
            pagination=PaginationModel.NONE,
            supported_query_styles=[QueryStyle.DIRECT_URL, QueryStyle.ENTITY_ID],
            languages=["*"],
            supported_intents=["general", "update", "patch"],
            rate_limit={},
            live_retrieval=False,
            availability_notes="Official facts are retrieved by explicit Fact Layer adapters, not a generic scraper.",
        )

    def search(self, plan: QueryPlan, cursor: str | None = None) -> SourcePage:
        raise SourceUnavailableError(
            "No generic official-page collector is configured; use an authorised Fact Layer adapter",
            error_code="official_adapter_not_configured",
        )

    def normalize(self, native_item: dict[str, Any], context: RetrievalContext) -> EvidenceItem:
        raise NotImplementedError("Official normalization is owned by Fact Layer adapters")
