"""Common request/response contracts for thin audience Mode renderers."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import AwareDatetime, Field, model_validator

from ..insights import CoverageReport
from ..models import ContractModel, Mode


class ModeRequest(ContractModel):
    request_id: str = Field(min_length=1)
    mode: Mode
    games: list[str] = Field(min_length=1, max_length=4)
    languages: list[str] = Field(default_factory=lambda: ["en"])
    preferences: str | dict[str, Any] | None = None
    research_intents: list[str] = Field(default_factory=list)
    private_dataset_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_mode_scope(self) -> "ModeRequest":
        if self.mode == Mode.COMPARE and len(self.games) < 2:
            raise ValueError("compare mode requires two to four games")
        if self.mode != Mode.COMPARE and len(self.games) != 1:
            raise ValueError(f"{self.mode.value} mode requires exactly one game")
        if self.private_dataset_ids:
            raise ValueError(
                "private datasets are interface-only in this checkpoint; public corpus only"
            )
        return self


class ModeClaim(ContractModel):
    claim_id: str = Field(pattern=r"^claim_.+")
    label: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    layer: Literal["fact", "player_evidence", "inference", "hypothesis", "insufficient"]
    taxonomy_node: str | None = None
    fact_ids: list[str] = Field(default_factory=list)
    insight_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    uncertainty: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_traceability(self) -> "ModeClaim":
        if self.layer == "fact" and (not self.fact_ids or not self.evidence_ids):
            raise ValueError("Fact Layer claims require fact and evidence IDs")
        if self.layer == "player_evidence" and (
            not self.insight_ids or not self.evidence_ids
        ):
            raise ValueError("Player Evidence claims require Insight and evidence IDs")
        if self.layer in {"inference", "hypothesis"} and not self.evidence_ids:
            raise ValueError("inferred and hypothesis claims require evidence IDs")
        return self


class EvidenceReference(ContractModel):
    evidence_id: str = Field(pattern=r"^ev_.+")
    game_id: str = Field(pattern=r"^game_.+")
    layer: Literal["fact", "player_evidence"]
    source: str
    source_url: str | None = None
    source_reference: str | None = None
    excerpt: str


class ModeResponse(ContractModel):
    request_id: str
    mode: Mode
    game_ids: list[str]
    payload: dict[str, Any]
    source_coverage: dict[str, CoverageReport]
    limitations: list[str]
    evidence_references: list[EvidenceReference]
    generated_at: AwareDatetime


def utc_now() -> datetime:
    from datetime import timezone

    return datetime.now(timezone.utc)
