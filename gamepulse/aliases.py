"""Evidence-backed alias discovery and deterministic search-safety rules."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from enum import Enum
from typing import Any, Callable, Protocol
from urllib.parse import quote_plus

from pydantic import Field, model_validator

from .models import (
    AliasType,
    AliasValidationStatus,
    Ambiguity,
    ContractModel,
    GameAlias,
    GameEntity,
    ResolutionStatus,
)
from .http import request_json


def normalize_alias(value: str) -> str:
    """Normalize for identity comparison while retaining the source spelling elsewhere."""

    value = unicodedata.normalize("NFKC", value).casefold().strip()
    return re.sub(r"[^\w\u3400-\u9fff]+", "", value, flags=re.UNICODE).replace("_", "")


def _alias_id(game_id: str, normalized_text: str) -> str:
    digest = hashlib.sha256(f"{game_id}:{normalized_text}".encode("utf-8")).hexdigest()[:20]
    return f"alias_{digest}"


class AliasEvidenceBasis(str, Enum):
    OFFICIAL_METADATA = "official_metadata"
    EDITORIAL_REFERENCE = "editorial_reference"
    COMMUNITY_SELF_REFERENCE = "community_self_reference"
    REPEATED_INDEPENDENT_USAGE = "repeated_independent_usage"
    AUTHORISED_RESEARCH = "authorised_research"
    PLATFORM_SEARCH_MATCH = "platform_search_match"
    CO_OCCURRENCE_ONLY = "co_occurrence_only"


class AliasObservation(ContractModel):
    text: str = Field(min_length=1)
    language: str | None
    proposed_type: AliasType
    source_evidence_ids: list[str]
    source_platforms: list[str]
    evidence_basis: AliasEvidenceBasis
    confidence: float = Field(ge=0, le=1)
    ambiguity: Ambiguity = Ambiguity.NONE
    ambiguity_notes: str | None = None
    platform_scope_required: bool = False
    source_references: list[str] = Field(default_factory=list)
    source_excerpts: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def evidence_references_align(self) -> "AliasObservation":
        if self.source_references and len(self.source_references) != len(self.source_evidence_ids):
            raise ValueError("source_references must be empty or align one-to-one with evidence IDs")
        if self.source_excerpts and len(self.source_excerpts) != len(self.source_evidence_ids):
            raise ValueError("source_excerpts must be empty or align one-to-one with evidence IDs")
        return self


class AliasReviewItem(ContractModel):
    alias_id: str
    text: str
    normalized_text: str
    validation_status: AliasValidationStatus
    reasons: list[str]
    source_evidence_ids: list[str]
    source_references: list[str]
    source_excerpts: list[str]


class AliasDiscoveryResult(ContractModel):
    game_id: str
    aliases: list[GameAlias]
    review_items: list[AliasReviewItem]
    observations: list[AliasObservation]

    def query_ready_aliases(self, *, include_scoped: bool = False) -> list[GameAlias]:
        allowed = {AliasValidationStatus.VALIDATED}
        if include_scoped:
            allowed.add(AliasValidationStatus.SCOPED_ONLY)
        return [alias for alias in self.aliases if alias.search_enabled and alias.validation_status in allowed]

    def standalone_aliases(self) -> list[GameAlias]:
        return [alias for alias in self.query_ready_aliases() if alias.standalone_search_safe]


class _MergedObservation(ContractModel):
    text: str
    normalized_text: str
    language: str | None
    proposed_type: AliasType
    source_evidence_ids: list[str]
    source_platforms: list[str]
    evidence_bases: list[AliasEvidenceBasis]
    confidence: float
    ambiguity: Ambiguity
    ambiguity_notes: list[str]
    platform_scope_required: bool
    source_references: list[str]
    source_excerpts: list[str]


_TYPE_PRIORITY = {
    AliasType.OFFICIAL_TITLE: 0,
    AliasType.LOCALIZED_TITLE: 1,
    AliasType.TRANSLITERATION: 2,
    AliasType.ABBREVIATION: 3,
    AliasType.COMMUNITY_NICKNAME: 4,
    AliasType.COMMON_MISSPELLING: 5,
}

_AMBIGUITY_PRIORITY = {
    Ambiguity.NONE: 0,
    Ambiguity.LOW: 1,
    Ambiguity.MEDIUM: 2,
    Ambiguity.HIGH: 3,
}

_CONFIDENCE_THRESHOLDS = {
    AliasType.ABBREVIATION: 0.75,
    AliasType.TRANSLITERATION: 0.75,
    AliasType.COMMUNITY_NICKNAME: 0.8,
    AliasType.COMMON_MISSPELLING: 0.85,
}


def _merge_observations(observations: list[AliasObservation]) -> list[_MergedObservation]:
    grouped: dict[str, list[AliasObservation]] = {}
    for observation in observations:
        normalized = normalize_alias(observation.text)
        if not normalized:
            continue
        grouped.setdefault(normalized, []).append(observation)

    merged: list[_MergedObservation] = []
    for normalized, items in grouped.items():
        selected_type = min((item.proposed_type for item in items), key=_TYPE_PRIORITY.get)
        selected_ambiguity = max((item.ambiguity for item in items), key=_AMBIGUITY_PRIORITY.get)
        merged.append(
            _MergedObservation(
                text=items[0].text,
                normalized_text=normalized,
                language=next((item.language for item in items if item.language), None),
                proposed_type=selected_type,
                source_evidence_ids=sorted({value for item in items for value in item.source_evidence_ids}),
                source_platforms=sorted({value for item in items for value in item.source_platforms}),
                evidence_bases=sorted(
                    {item.evidence_basis for item in items}, key=lambda value: value.value,
                ),
                confidence=max(item.confidence for item in items),
                ambiguity=selected_ambiguity,
                ambiguity_notes=sorted({item.ambiguity_notes for item in items if item.ambiguity_notes}),
                platform_scope_required=any(item.platform_scope_required for item in items),
                source_references=sorted({value for item in items for value in item.source_references}),
                source_excerpts=sorted({value for item in items for value in item.source_excerpts}),
            )
        )
    return sorted(merged, key=lambda item: (item.normalized_text, item.text))


def _validate_observation(item: _MergedObservation) -> tuple[AliasValidationStatus, bool, bool, list[str]]:
    reasons: list[str] = []
    if not item.source_evidence_ids:
        return AliasValidationStatus.REJECTED, False, False, ["no alias evidence supplied"]
    if AliasEvidenceBasis.CO_OCCURRENCE_ONLY in item.evidence_bases:
        return (
            AliasValidationStatus.PENDING,
            False,
            False,
            ["co-occurrence alone is not sufficient alias evidence"],
        )

    reliable_bases = {
        AliasEvidenceBasis.OFFICIAL_METADATA,
        AliasEvidenceBasis.EDITORIAL_REFERENCE,
        AliasEvidenceBasis.COMMUNITY_SELF_REFERENCE,
        AliasEvidenceBasis.REPEATED_INDEPENDENT_USAGE,
        AliasEvidenceBasis.AUTHORISED_RESEARCH,
        AliasEvidenceBasis.PLATFORM_SEARCH_MATCH,
    }
    if not (set(item.evidence_bases) & reliable_bases):
        return AliasValidationStatus.PENDING, False, False, ["evidence basis requires review"]

    if item.ambiguity == Ambiguity.HIGH:
        if item.confidence >= 0.6 and item.source_platforms:
            return (
                AliasValidationStatus.SCOPED_ONLY,
                True,
                False,
                ["high-ambiguity alias requires a platform or canonical-title disambiguator"],
            )
        return AliasValidationStatus.REJECTED, False, False, ["high ambiguity without a usable scope"]

    if item.ambiguity == Ambiguity.MEDIUM or item.platform_scope_required:
        reasons.append("alias is usable only with source or entity context")
        return AliasValidationStatus.SCOPED_ONLY, True, False, reasons

    threshold = _CONFIDENCE_THRESHOLDS.get(item.proposed_type, 0.8)
    independent_evidence = len(item.source_evidence_ids)
    if item.proposed_type == AliasType.COMMUNITY_NICKNAME and independent_evidence < 2:
        return (
            AliasValidationStatus.PENDING,
            False,
            False,
            ["community nickname requires at least two evidence records"],
        )
    if item.confidence < threshold:
        return (
            AliasValidationStatus.PENDING,
            False,
            False,
            [f"confidence {item.confidence:.2f} is below {threshold:.2f} for {item.proposed_type.value}"],
        )

    reasons.append("evidence and confidence meet the deterministic validation threshold")
    standalone_safe = item.ambiguity == Ambiguity.NONE
    if item.ambiguity == Ambiguity.LOW:
        reasons.append("low ambiguity retained; standalone search disabled")
    return AliasValidationStatus.VALIDATED, True, standalone_safe, reasons


def _official_observations(game: GameEntity) -> list[AliasObservation]:
    evidence_ids = list(game.resolution_evidence_ids)
    if not evidence_ids:
        raise ValueError("resolved game metadata must retain evidence before alias discovery")
    observations: list[AliasObservation] = [
        AliasObservation(
            text=game.canonical_title,
            language=next(
                (language for language, title in game.localized_titles.items() if title == game.canonical_title),
                None,
            ),
            proposed_type=AliasType.OFFICIAL_TITLE,
            source_evidence_ids=evidence_ids,
            source_platforms=["all"],
            evidence_basis=AliasEvidenceBasis.OFFICIAL_METADATA,
            confidence=1,
            ambiguity=Ambiguity.NONE,
        )
    ]
    for language, title in game.localized_titles.items():
        observations.append(
            AliasObservation(
                text=title,
                language=language,
                proposed_type=(
                    AliasType.OFFICIAL_TITLE if title == game.canonical_title else AliasType.LOCALIZED_TITLE
                ),
                source_evidence_ids=evidence_ids,
                source_platforms=["all"],
                evidence_basis=AliasEvidenceBasis.OFFICIAL_METADATA,
                confidence=1,
                ambiguity=Ambiguity.NONE,
            )
        )
    if game.original_title:
        observations.append(
            AliasObservation(
                text=game.original_title,
                language=None,
                proposed_type=AliasType.OFFICIAL_TITLE,
                source_evidence_ids=evidence_ids,
                source_platforms=["all"],
                evidence_basis=AliasEvidenceBasis.OFFICIAL_METADATA,
                confidence=1,
                ambiguity=Ambiguity.NONE,
            )
        )
    return observations


def discover_aliases(
    game: GameEntity,
    observations: list[AliasObservation] | None = None,
) -> AliasDiscoveryResult:
    """Build validated aliases for one resolved game without retrieving social content."""

    if game.resolution_status != ResolutionStatus.RESOLVED:
        raise ValueError("alias discovery requires a resolved canonical game")
    supplied = list(observations or [])
    all_observations = _official_observations(game) + supplied
    aliases: list[GameAlias] = []
    review_items: list[AliasReviewItem] = []
    for item in _merge_observations(all_observations):
        if item.proposed_type in {AliasType.OFFICIAL_TITLE, AliasType.LOCALIZED_TITLE}:
            status, enabled, standalone, reasons = (
                AliasValidationStatus.VALIDATED,
                True,
                True,
                ["official or localized title from resolved metadata"],
            )
            confidence = 1.0
            ambiguity = Ambiguity.NONE
        else:
            status, enabled, standalone, reasons = _validate_observation(item)
            confidence = item.confidence
            ambiguity = item.ambiguity

        alias = GameAlias(
            alias_id=_alias_id(game.game_id, item.normalized_text),
            game_id=game.game_id,
            text=item.text,
            normalized_text=item.normalized_text,
            language=item.language,
            alias_type=item.proposed_type,
            source_evidence_ids=item.source_evidence_ids,
            source_platforms=item.source_platforms,
            confidence=confidence,
            ambiguity=ambiguity,
            ambiguity_notes="; ".join(item.ambiguity_notes) or None,
            validation_status=status,
            search_enabled=enabled,
            standalone_search_safe=standalone,
        )
        aliases.append(alias)
        if status != AliasValidationStatus.VALIDATED:
            review_items.append(
                AliasReviewItem(
                    alias_id=alias.alias_id,
                    text=alias.text,
                    normalized_text=alias.normalized_text,
                    validation_status=status,
                    reasons=reasons,
                    source_evidence_ids=item.source_evidence_ids,
                    source_references=item.source_references,
                    source_excerpts=item.source_excerpts,
                )
            )

    aliases.sort(key=lambda alias: (_TYPE_PRIORITY[alias.alias_type], alias.normalized_text))
    return AliasDiscoveryResult(
        game_id=game.game_id,
        aliases=aliases,
        review_items=review_items,
        observations=supplied,
    )


class AliasObservationProvider(Protocol):
    name: str

    def discover(self, game: GameEntity) -> list[AliasObservation]: ...


def _abbreviation_candidates(game: GameEntity) -> list[tuple[str, str | None]]:
    candidates: dict[str, tuple[str, str | None]] = {}
    for language, title in game.localized_titles.items():
        tokens = re.findall(r"[A-Za-z]+|\d+", title)
        for token in tokens:
            if token.isupper() and 2 <= len(token) <= 6:
                key = normalize_alias(token)
                current = candidates.get(key)
                if current is None or language.casefold().startswith("en"):
                    candidates[key] = (token, language)
        meaningful = [token for token in tokens if token.casefold() not in {"a", "an", "the", "of", "and"}]
        if len(meaningful) >= 2:
            abbreviation = "".join(token if token.isdigit() else token[0].upper() for token in meaningful)
            if 2 <= len(abbreviation) <= 6 and normalize_alias(abbreviation) != normalize_alias(title):
                key = normalize_alias(abbreviation)
                current = candidates.get(key)
                if current is None or language.casefold().startswith("en"):
                    candidates[key] = (abbreviation, language)
    return sorted(candidates.values(), key=lambda item: (item[0].casefold(), item[1] or ""))


class SteamAliasObservationProvider:
    """Validate derived abbreviations against Steam's own search index."""

    name = "steam_alias_search"

    def __init__(self, requester: Callable[..., Any] = request_json):
        self.requester = requester

    def discover(self, game: GameEntity) -> list[AliasObservation]:
        app_id = game.external_ids.get("steam_app_id")
        if not app_id:
            return []
        observations: list[AliasObservation] = []
        for candidate, language in _abbreviation_candidates(game):
            is_zh = bool(language and language.casefold().startswith("zh"))
            payload = self.requester(
                "https://store.steampowered.com/api/storesearch/",
                params={
                    "term": candidate,
                    "l": "schinese" if is_zh else "english",
                    "cc": "CN" if is_zh else "US",
                },
                headers={"User-Agent": "PlayerVoice/0.3"},
                retries=2,
                timeout=20,
            )
            results = payload.get("items") or []
            matching_positions = [
                index for index, item in enumerate(results[:10]) if str(item.get("id")) == str(app_id)
            ]
            if not matching_positions:
                continue
            rank = matching_positions[0]
            competing_results = [item for item in results[:5] if str(item.get("id")) != str(app_id)]
            normalized = normalize_alias(candidate)
            if len(normalized) <= 3 and competing_results:
                ambiguity = Ambiguity.HIGH
            elif competing_results:
                ambiguity = Ambiguity.MEDIUM
            else:
                ambiguity = Ambiguity.NONE
            reference = f"https://store.steampowered.com/search/?term={quote_plus(candidate)}"
            evidence_id = f"ev_alias_{hashlib.sha256(f'steam:{candidate}:{app_id}'.encode()).hexdigest()[:20]}"
            observations.append(
                AliasObservation(
                    text=candidate,
                    language=language,
                    proposed_type=AliasType.ABBREVIATION,
                    source_evidence_ids=[evidence_id],
                    source_platforms=["steam"],
                    evidence_basis=AliasEvidenceBasis.PLATFORM_SEARCH_MATCH,
                    confidence=0.95 if rank == 0 else 0.8,
                    ambiguity=ambiguity,
                    ambiguity_notes=(
                        f"Steam search returned {len(competing_results)} competing top-five result(s)"
                        if competing_results else None
                    ),
                    platform_scope_required=ambiguity != Ambiguity.NONE,
                    source_references=[reference],
                    source_excerpts=[json.dumps(results[:5], ensure_ascii=False, sort_keys=True)],
                )
            )
        return observations
