"""Validated domain contracts for the PlayerVoice intelligence core."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


JsonValue = str | int | float | bool | list[Any] | dict[str, Any]


class ContractModel(BaseModel):
    """Shared strict serialization behaviour for persisted contracts."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, value: dict[str, Any]):
        return cls.model_validate(value)


class ResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    NEEDS_CHOICE = "needs_choice"
    UNRESOLVED = "unresolved"


class GameEntity(ContractModel):
    game_id: str = Field(pattern=r"^game_.+")
    canonical_title: str = Field(min_length=1)
    original_title: str | None
    localized_titles: dict[str, str]
    external_ids: dict[str, str]
    developers: list[str]
    publishers: list[str]
    resolution_status: ResolutionStatus
    resolution_confidence: float = Field(ge=0, le=1)
    resolution_evidence_ids: list[str]
    resolved_at: AwareDatetime
    release_dates: dict[str, str] = Field(default_factory=dict)
    genres: list[str] = Field(default_factory=list)
    franchise: str | None = None
    official_urls: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)


class AliasType(str, Enum):
    OFFICIAL_TITLE = "official_title"
    LOCALIZED_TITLE = "localized_title"
    ABBREVIATION = "abbreviation"
    TRANSLITERATION = "transliteration"
    COMMUNITY_NICKNAME = "community_nickname"
    COMMON_MISSPELLING = "common_misspelling"


class Ambiguity(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AliasValidationStatus(str, Enum):
    VALIDATED = "validated"
    SCOPED_ONLY = "scoped_only"
    REJECTED = "rejected"
    PENDING = "pending"


class GameAlias(ContractModel):
    alias_id: str = Field(pattern=r"^alias_.+")
    game_id: str = Field(pattern=r"^game_.+")
    text: str = Field(min_length=1)
    normalized_text: str = Field(min_length=1)
    language: str | None
    alias_type: AliasType
    source_evidence_ids: list[str]
    source_platforms: list[str]
    confidence: float = Field(ge=0, le=1)
    ambiguity: Ambiguity
    ambiguity_notes: str | None = None
    validation_status: AliasValidationStatus
    search_enabled: bool
    standalone_search_safe: bool

    @model_validator(mode="after")
    def enforce_search_safety(self) -> "GameAlias":
        if self.ambiguity == Ambiguity.HIGH and self.standalone_search_safe:
            raise ValueError("high-ambiguity aliases cannot be standalone-search safe")
        if self.validation_status == AliasValidationStatus.REJECTED and self.search_enabled:
            raise ValueError("rejected aliases cannot be search enabled")
        return self


class SourceAuthority(str, Enum):
    OFFICIAL = "official"
    PLATFORM_STORE = "platform_store"
    REPUTABLE_THIRD_PARTY = "reputable_third_party"


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    CONFLICTING = "conflicting"
    UNVERIFIED = "unverified"


class FactRecord(ContractModel):
    fact_id: str = Field(pattern=r"^fact_.+")
    game_id: str = Field(pattern=r"^game_.+")
    fact_type: str = Field(min_length=1)
    value: JsonValue
    unit: str | None = None
    valid_from: AwareDatetime | None = None
    valid_to: AwareDatetime | None = None
    territory: str | None = None
    platform: str | None = None
    source_evidence_id: str = Field(min_length=1)
    source_authority: SourceAuthority
    verification_status: VerificationStatus
    confidence: float = Field(ge=0, le=1)
    retrieved_at: AwareDatetime


class QueryIntent(str, Enum):
    GENERAL = "general"
    REVIEW = "review"
    PERFORMANCE = "performance"
    OPTIMISATION = "optimisation"
    GRAPHICS = "graphics"
    AUDIO = "audio"
    CONTROLS = "controls"
    BUGS = "bugs"
    STORY = "story"
    CHARACTERS = "characters"
    COMBAT = "combat"
    EXPLORATION = "exploration"
    PROGRESSION = "progression"
    GRIND = "grind"
    DAILY = "daily"
    MONETISATION = "monetisation"
    GACHA = "gacha"
    PVP = "pvp"
    ENDGAME = "endgame"
    CHURN = "churn"
    UNINSTALL = "uninstall"
    FEATURE_REQUEST = "feature_request"
    UPDATE = "update"
    PATCH = "patch"
    CONTROVERSY = "controversy"


class ExpectedEvidenceKind(str, Enum):
    FACT = "fact"
    PATCH_NOTE = "patch_note"
    REVIEW = "review"
    POST = "post"
    COMMENT = "comment"
    VIDEO = "video"


class QueryPlan(ContractModel):
    query_id: str = Field(pattern=r"^query_.+")
    run_id: str = Field(pattern=r"^run_.+")
    game_id: str = Field(pattern=r"^game_.+")
    source: str = Field(min_length=1)
    language: str = Field(min_length=1)
    intent: QueryIntent
    query_text: str = Field(min_length=1)
    alias_ids: list[str]
    disambiguators: list[str]
    expected_evidence_kind: ExpectedEvidenceKind
    generated_at: AwareDatetime


class EvidenceKind(str, Enum):
    OFFICIAL = "official"
    FACT_SOURCE = "fact_source"
    PATCH_NOTE = "patch_note"
    REVIEW = "review"
    POST = "post"
    COMMENT = "comment"
    VIDEO = "video"
    SURVEY_RESPONSE = "survey_response"
    SUPPORT_RECORD = "support_record"


class AccessScope(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"


class RetrievalMethod(str, Enum):
    API = "api"
    PUBLIC_ENDPOINT = "public_endpoint"
    OFFICIAL_FEED = "official_feed"
    LICENSED_PROVIDER = "licensed_provider"
    AUTHORISED_EXPORT = "authorised_export"
    USER_UPLOAD = "user_upload"


class RelevanceLabel(str, Enum):
    RELEVANT = "relevant"
    AMBIGUOUS = "ambiguous"
    IRRELEVANT = "irrelevant"
    PENDING = "pending"


class SourceClass(str, Enum):
    OFFICIAL = "official"
    PLATFORM_STORE = "platform_store"
    PUBLIC_COMMUNITY = "public_community"
    LICENSED_PROVIDER = "licensed_provider"
    USER_PROVIDED = "user_provided"
    INTERNAL = "internal"


class RedactionStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    REDACTED = "redacted"
    PENDING = "pending"


class Provenance(ContractModel):
    source_class: SourceClass
    collector_version: str = Field(min_length=1)
    terms_or_permission_reference: str | None = None
    content_checksum: str = Field(min_length=1)
    raw_snapshot_reference: str | None = None
    contains_personal_data: bool = False
    redaction_status: RedactionStatus = RedactionStatus.NOT_REQUIRED


class EvidenceItem(ContractModel):
    evidence_id: str = Field(pattern=r"^ev_.+")
    game_id: str = Field(pattern=r"^game_.+")
    evidence_kind: EvidenceKind
    access_scope: AccessScope
    dataset_id: str | None
    source: str = Field(min_length=1)
    source_content_id: str = Field(min_length=1)
    parent_evidence_id: str | None = None
    source_url: str | None = None
    source_reference: str | None = None
    title: str | None = None
    original_text: str = Field(min_length=1)
    normalized_text: str | None = None
    language: str | None
    published_at: AwareDatetime | None
    retrieved_at: AwareDatetime
    run_id: str = Field(pattern=r"^run_.+")
    query_id: str | None = None
    matched_alias_ids: list[str]
    retrieval_method: RetrievalMethod
    relevance_label: RelevanceLabel
    relevance_score: float | None = Field(default=None, ge=0, le=1)
    relevance_reasons: list[str]
    relevance_method_version: str | None = None
    recommended: bool | None = None
    rating: float | None = None
    rating_scale: str | dict[str, Any] | None = None
    engagement: float | dict[str, int | float] | None = None
    reply_count: int | None = Field(default=None, ge=0)
    playtime_hours: float | None = Field(default=None, ge=0)
    platform: str | None = None
    hardware_context: str | dict[str, Any] | None = None
    version_context: str | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance

    @model_validator(mode="after")
    def isolate_access_scope(self) -> "EvidenceItem":
        if self.access_scope == AccessScope.PRIVATE and not self.dataset_id:
            raise ValueError("private evidence requires dataset_id")
        if self.access_scope == AccessScope.PUBLIC and self.dataset_id is not None:
            raise ValueError("public evidence cannot be assigned to a private dataset")
        return self


class SentimentLabel(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    MIXED = "mixed"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


class AnalysisAnnotation(ContractModel):
    annotation_id: str = Field(pattern=r"^annotation_.+")
    evidence_id: str = Field(pattern=r"^ev_.+")
    taxonomy_version: str = Field(min_length=1)
    primary_topic: str | None
    secondary_topics: list[str]
    sentiment_label: SentimentLabel
    sentiment_score: float | None = Field(default=None, ge=-1, le=1)
    pain_points: list[str]
    underlying_needs: list[str]
    explicit_feature_requests: list[str]
    behaviour_signals: list[str]
    analysis_confidence: float = Field(ge=0, le=1)
    method: dict[str, Any]
    requires_human_review: bool


class InsightScope(str, Enum):
    GAME = "game"
    COMPARISON = "comparison"
    PATCH = "patch"
    SEGMENT = "segment"


class Mode(str, Enum):
    PLAYER = "player"
    CREATOR = "creator"
    ANALYST = "analyst"
    COMPARE = "compare"


class InsightType(str, Enum):
    FACT_SUMMARY = "fact_summary"
    PRAISE = "praise"
    COMPLAINT = "complaint"
    CONTROVERSY = "controversy"
    PAIN_POINT = "pain_point"
    NEED = "need"
    OPPORTUNITY = "opportunity"
    DIFFERENCE = "difference"
    PREFERENCE_MATCH = "preference_match"
    RESEARCH_GAP = "research_gap"


class Insight(ContractModel):
    insight_id: str = Field(pattern=r"^insight_.+")
    scope_type: InsightScope
    scope_ids: list[str] = Field(min_length=1)
    mode: Mode
    insight_type: InsightType
    statement: str = Field(min_length=1)
    taxonomy_nodes: list[str]
    confidence: float = Field(ge=0, le=1)
    supporting_evidence_ids: list[str]
    challenging_evidence_ids: list[str]
    context_evidence_ids: list[str]
    sample_scope: dict[str, Any]
    uncertainty: list[str]
    priority: dict[str, Any] | None = None
    opportunity_origin: Literal["explicit_request", "inferred_need"] | None = None
    generated_at: AwareDatetime

    @model_validator(mode="after")
    def require_evidence_links(self) -> "Insight":
        links = self.supporting_evidence_ids + self.challenging_evidence_ids + self.context_evidence_ids
        if not links:
            raise ValueError("insights require at least one evidence link")
        if self.insight_type == InsightType.OPPORTUNITY and self.opportunity_origin is None:
            raise ValueError("opportunities must identify explicit-request or inferred-need origin")
        return self


class ReleaseType(str, Enum):
    RELEASE = "release"
    MAJOR_UPDATE = "major_update"
    PATCH = "patch"
    HOTFIX = "hotfix"


class PatchRecord(ContractModel):
    patch_id: str = Field(pattern=r"^patch_.+")
    game_id: str = Field(pattern=r"^game_.+")
    release_type: ReleaseType
    version: str | None
    title: str = Field(min_length=1)
    published_at: AwareDatetime
    effective_at: AwareDatetime
    platforms: list[str]
    territories: list[str]
    change_items: list[dict[str, Any]]
    official_evidence_ids: list[str]
    previous_patch_id: str | None = None


class PrivateSourceType(str, Enum):
    CSV = "csv"
    JSON = "json"
    EXCEL = "excel"
    SURVEY = "survey"
    SUPPORT_EXPORT = "support_export"
    COMMUNITY_EXPORT = "community_export"
    RESEARCH_DATASET = "research_dataset"


class DatasetStatus(str, Enum):
    VALIDATING = "validating"
    READY = "ready"
    REJECTED = "rejected"
    DELETED = "deleted"


class PrivateDataset(ContractModel):
    dataset_id: str = Field(pattern=r"^dataset_.+")
    owner_scope: str = Field(min_length=1)
    name: str = Field(min_length=1)
    source_type: PrivateSourceType
    authorisation_attested: bool
    schema_mapping: dict[str, str]
    allowed_modes: list[Mode]
    retention_policy: dict[str, Any]
    created_at: AwareDatetime
    status: DatasetStatus

    @model_validator(mode="after")
    def require_authorisation_for_ready_data(self) -> "PrivateDataset":
        if self.status == DatasetStatus.READY and not self.authorisation_attested:
            raise ValueError("ready private datasets require authorisation attestation")
        return self


class SourceRunState(str, Enum):
    COLLECTED = "collected"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"
    FAILED = "failed"


class SourceRunStatus(ContractModel):
    status: SourceRunState
    queries_attempted: int = Field(default=0, ge=0)
    items_retrieved: int = Field(default=0, ge=0)
    items_relevant: int = Field(default=0, ge=0)
    items_ambiguous: int = Field(default=0, ge=0)
    items_irrelevant: int = Field(default=0, ge=0)
    duplicates: int = Field(default=0, ge=0)
    error_code: str | None = None
    reason: str | None = None


class CollectionRun(ContractModel):
    run_id: str = Field(pattern=r"^run_.+")
    request_hash: str = Field(min_length=1)
    game_ids: list[str] = Field(min_length=1)
    query_plans: list[QueryPlan]
    code_version: str = Field(min_length=1)
    config_version: str = Field(min_length=1)
    taxonomy_version: str = Field(min_length=1)
    started_at: AwareDatetime
    ended_at: AwareDatetime | None = None
    source_status: dict[str, SourceRunStatus]

    @model_validator(mode="after")
    def validate_run_scope(self) -> "CollectionRun":
        if self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError("ended_at cannot precede started_at")
        if any(plan.run_id != self.run_id for plan in self.query_plans):
            raise ValueError("all query plans must belong to the collection run")
        return self


SCHEMA_MODELS: dict[str, type[ContractModel]] = {
    "game_entity.schema.json": GameEntity,
    "fact_record.schema.json": FactRecord,
    "evidence_item.schema.json": EvidenceItem,
    "insight.schema.json": Insight,
    "run_manifest.schema.json": CollectionRun,
}


def iso_now() -> datetime:
    """Return a timezone-aware timestamp for callers constructing contracts."""

    return datetime.now().astimezone()
