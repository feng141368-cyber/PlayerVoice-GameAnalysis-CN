"""Deterministic, inspectable relevance scoring for retrieved community evidence."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable

from pydantic import Field, model_validator

from .models import (
    AliasValidationStatus,
    Ambiguity,
    ContractModel,
    EvidenceItem,
    GameAlias,
    GameEntity,
    RelevanceLabel,
)


BASE_RELEVANCE_VERSION = "relevance-rules-v1"


class RelevanceSettings(ContractModel):
    relevant_threshold: float = Field(default=0.70, ge=0, le=1)
    ambiguous_threshold: float = Field(default=0.25, ge=0, le=1)
    official_title_weight: float = Field(default=0.78, ge=0, le=1)
    safe_alias_weight: float = Field(default=0.55, ge=0, le=1)
    ambiguous_alias_weight: float = Field(default=0.20, ge=0, le=1)
    developer_publisher_weight: float = Field(default=0.30, ge=0, le=1)
    game_term_weight: float = Field(default=0.45, ge=0, le=1)
    context_cue_weight: float = Field(default=0.15, ge=0, le=1)
    query_context_weight: float = Field(default=0.05, ge=0, le=1)
    competing_entity_penalty: float = Field(default=0.85, ge=0, le=1)
    method_version: str = BASE_RELEVANCE_VERSION

    @model_validator(mode="after")
    def validate_threshold_order(self) -> "RelevanceSettings":
        if self.ambiguous_threshold >= self.relevant_threshold:
            raise ValueError("ambiguous_threshold must be lower than relevant_threshold")
        return self


class RelevanceDecision(ContractModel):
    label: RelevanceLabel
    score: float = Field(ge=0, le=1)
    reasons: list[str]
    signals: dict[str, Any]
    method_version: str


class RelevanceEvaluation(ContractModel):
    evidence: EvidenceItem
    decision: RelevanceDecision


class RelevanceFixtureSummary(ContractModel):
    total: int
    relevant_expected: int
    relevant_predicted: int
    true_positive: int
    false_positive: int
    false_negative: int
    precision: float
    recall: float


def _normalise(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^\w\u3400-\u9fff]+", " ", value).strip()


def _contains(text: str, phrase: str) -> bool:
    needle = _normalise(phrase)
    if not needle:
        return False
    if re.search(r"[\u3400-\u9fff]", needle):
        return needle.replace(" ", "") in text.replace(" ", "")
    return f" {needle} " in f" {text} "


def _method_version(
    settings: RelevanceSettings,
    *,
    game_terms: Iterable[str],
    competing_entities: Iterable[str],
) -> str:
    payload = {
        "settings": settings.to_dict(),
        "game_terms": sorted({_normalise(value) for value in game_terms if _normalise(value)}),
        "competing_entities": sorted(
            {_normalise(value) for value in competing_entities if _normalise(value)}
        ),
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:12]
    return f"{settings.method_version}+{digest}"


def _official_titles(game: GameEntity) -> list[str]:
    values = [game.canonical_title, game.original_title, *game.localized_titles.values()]
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        normalised = _normalise(value)
        if normalised and normalised not in seen:
            seen.add(normalised)
            unique.append(value)
    return unique


def _native_entity_signal(evidence: EvidenceItem, game: GameEntity) -> tuple[str | None, bool | None]:
    metadata = evidence.source_metadata
    if evidence.source == "steam" and game.external_ids.get("steam_app_id"):
        expected = str(game.external_ids["steam_app_id"])
        actual = metadata.get("app_id")
        if actual is not None:
            return f"steam_app_id={actual}", str(actual) == expected
    expected_key = f"{evidence.source}_id"
    if game.external_ids.get(expected_key) and metadata.get(expected_key) is not None:
        expected = str(game.external_ids[expected_key])
        actual = str(metadata[expected_key])
        return f"{expected_key}={actual}", actual == expected
    return None, None


def evaluate_relevance(
    evidence: EvidenceItem,
    game: GameEntity,
    aliases: Iterable[GameAlias],
    *,
    game_terms: Iterable[str] = (),
    competing_entities: Iterable[str] = (),
    settings: RelevanceSettings | None = None,
) -> RelevanceEvaluation:
    """Evaluate one record without using sentiment as a relevance feature."""

    settings = settings or RelevanceSettings()
    terms = list(game_terms)
    competitors = list(competing_entities)
    method_version = _method_version(settings, game_terms=terms, competing_entities=competitors)
    combined = _normalise(" ".join(value for value in [evidence.title or "", evidence.original_text] if value))
    reasons: list[str] = []
    signals: dict[str, Any] = {
        "positive": [],
        "negative": [],
        "matched_alias_ids": [],
        "matched_game_terms": [],
    }

    if evidence.game_id != game.game_id:
        reasons.append("game_id_mismatch")
        signals["negative"].append("game_id_mismatch")
        decision = RelevanceDecision(
            label=RelevanceLabel.IRRELEVANT,
            score=0,
            reasons=reasons,
            signals=signals,
            method_version=method_version,
        )
        return _apply_decision(evidence, decision)

    score = 0.0
    native_signal, native_match = _native_entity_signal(evidence, game)
    if native_match is True:
        score = 0.99
        reasons.append(f"source_native_id_match:{native_signal}")
        signals["positive"].append("source_native_id_match")
    elif native_match is False:
        reasons.append(f"source_native_id_mismatch:{native_signal}")
        signals["negative"].append("source_native_id_mismatch")
        decision = RelevanceDecision(
            label=RelevanceLabel.IRRELEVANT,
            score=0,
            reasons=reasons,
            signals=signals,
            method_version=method_version,
        )
        return _apply_decision(evidence, decision)

    matched_official = [title for title in _official_titles(game) if _contains(combined, title)]
    if matched_official:
        score += settings.official_title_weight
        reasons.append(f"official_title_match:{matched_official[0]}")
        signals["positive"].append("official_title_match")

    official_normalised = {_normalise(value) for value in _official_titles(game)}
    matched_aliases: list[GameAlias] = []
    for alias in aliases:
        if alias.game_id != game.game_id or not alias.search_enabled:
            continue
        if alias.validation_status not in {
            AliasValidationStatus.VALIDATED,
            AliasValidationStatus.SCOPED_ONLY,
        }:
            continue
        if _normalise(alias.text) in official_normalised:
            continue
        if _contains(combined, alias.text):
            matched_aliases.append(alias)
            signals["matched_alias_ids"].append(alias.alias_id)
            reasons.append(
                f"alias_match:{alias.text} ({alias.ambiguity.value}, {alias.validation_status.value})"
            )
    if matched_aliases:
        if any(alias.standalone_search_safe for alias in matched_aliases):
            score += settings.safe_alias_weight
            signals["positive"].append("safe_alias_match")
        else:
            score += settings.ambiguous_alias_weight
            signals["positive"].append("scoped_alias_match")

    entity_names = [*game.developers, *game.publishers]
    matched_entities = [value for value in entity_names if _contains(combined, value)]
    if matched_entities:
        score += settings.developer_publisher_weight
        reasons.append(f"developer_publisher_match:{matched_entities[0]}")
        signals["positive"].append("developer_publisher_match")

    matched_terms = [value for value in terms if _contains(combined, value)]
    if matched_terms:
        score += min(settings.game_term_weight * len(matched_terms), settings.game_term_weight * 1.5)
        reasons.extend(f"game_term_match:{value}" for value in matched_terms[:3])
        signals["matched_game_terms"] = matched_terms
        signals["positive"].append("game_term_match")

    context_cues = [
        cue
        for cue in ["update", "patch", "fps", "stutter", "server", "ranked", "matchmaking", "更新", "补丁", "帧", "卡顿", "服务器"]
        if _contains(combined, cue)
    ]
    if matched_aliases and len(context_cues) >= 2:
        score += settings.context_cue_weight
        reasons.append(f"surrounding_context:{','.join(context_cues[:4])}")
        signals["positive"].append("surrounding_context")

    query_provenance = evidence.source_metadata.get("query_provenance")
    if isinstance(query_provenance, dict) and query_provenance.get("canonical_game_id") == game.game_id:
        score += settings.query_context_weight
        reasons.append("query_provenance_game_id_match")
        signals["positive"].append("query_provenance_game_id_match")

    matched_competitors = [value for value in competitors if _contains(combined, value)]
    if matched_competitors:
        score -= settings.competing_entity_penalty
        reasons.append(f"competing_entity_match:{matched_competitors[0]}")
        signals["negative"].append("competing_entity_match")

    score = round(max(0.0, min(1.0, score)), 4)
    unsafe_alias_only = bool(matched_aliases) and all(
        alias.ambiguity in {Ambiguity.MEDIUM, Ambiguity.HIGH} or not alias.standalone_search_safe
        for alias in matched_aliases
    ) and not (matched_official or matched_entities or matched_terms or native_match is True)

    if matched_competitors and native_match is not True and score < settings.relevant_threshold:
        label = RelevanceLabel.IRRELEVANT
    elif score >= settings.relevant_threshold and not unsafe_alias_only:
        label = RelevanceLabel.RELEVANT
    elif score >= settings.ambiguous_threshold or matched_aliases or matched_official:
        label = RelevanceLabel.AMBIGUOUS
        if unsafe_alias_only:
            reasons.append("ambiguous_alias_without_independent_game_context")
            signals["negative"].append("ambiguous_alias_only")
    else:
        label = RelevanceLabel.IRRELEVANT
        reasons.append("insufficient_game_specific_evidence")

    decision = RelevanceDecision(
        label=label,
        score=score,
        reasons=reasons,
        signals=signals,
        method_version=method_version,
    )
    return _apply_decision(evidence, decision)


def _apply_decision(evidence: EvidenceItem, decision: RelevanceDecision) -> RelevanceEvaluation:
    metadata = dict(evidence.source_metadata)
    metadata["relevance_signals"] = decision.signals
    evaluated = evidence.model_copy(
        update={
            "relevance_label": decision.label,
            "relevance_score": decision.score,
            "relevance_reasons": list(decision.reasons),
            "relevance_method_version": decision.method_version,
            "source_metadata": metadata,
        }
    )
    return RelevanceEvaluation(evidence=evaluated, decision=decision)


def relevant_only(evaluations: Iterable[RelevanceEvaluation]) -> list[EvidenceItem]:
    return [
        result.evidence
        for result in evaluations
        if result.decision.label == RelevanceLabel.RELEVANT
    ]


def review_queue_rows(evaluations: Iterable[RelevanceEvaluation]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in evaluations:
        if result.decision.label != RelevanceLabel.AMBIGUOUS:
            continue
        item = result.evidence
        rows.append(
            {
                "evidence_id": item.evidence_id,
                "game_id": item.game_id,
                "source": item.source,
                "source_content_id": item.source_content_id,
                "title": item.title,
                "original_text": item.original_text,
                "source_url": item.source_url,
                "query_id": item.query_id,
                "relevance_score": result.decision.score,
                "relevance_label": result.decision.label.value,
                "relevance_reasons": list(result.decision.reasons),
                "relevance_method_version": result.decision.method_version,
                "query_provenance": item.source_metadata.get("query_provenance"),
            }
        )
    return rows


def write_review_queue(evaluations: Iterable[RelevanceEvaluation], output: Path) -> int:
    rows = review_queue_rows(evaluations)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.casefold() == ".json":
        output.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif output.suffix.casefold() == ".csv":
        fieldnames = list(rows[0]) if rows else [
            "evidence_id", "game_id", "source", "source_content_id", "title", "original_text",
            "source_url", "query_id", "relevance_score", "relevance_label", "relevance_reasons",
            "relevance_method_version", "query_provenance",
        ]
        with output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        **row,
                        "relevance_reasons": json.dumps(row["relevance_reasons"], ensure_ascii=False),
                        "query_provenance": json.dumps(row["query_provenance"], ensure_ascii=False),
                    }
                )
    else:
        raise ValueError("review queue output must use .json or .csv")
    return len(rows)


def summarize_fixture_labels(
    evaluations: Iterable[tuple[RelevanceEvaluation, RelevanceLabel | str]],
) -> RelevanceFixtureSummary:
    pairs = [(result.decision.label, RelevanceLabel(expected)) for result, expected in evaluations]
    true_positive = sum(predicted == expected == RelevanceLabel.RELEVANT for predicted, expected in pairs)
    false_positive = sum(
        predicted == RelevanceLabel.RELEVANT and expected != RelevanceLabel.RELEVANT
        for predicted, expected in pairs
    )
    false_negative = sum(
        predicted != RelevanceLabel.RELEVANT and expected == RelevanceLabel.RELEVANT
        for predicted, expected in pairs
    )
    relevant_predicted = true_positive + false_positive
    relevant_expected = true_positive + false_negative
    return RelevanceFixtureSummary(
        total=len(pairs),
        relevant_expected=relevant_expected,
        relevant_predicted=relevant_predicted,
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        precision=(true_positive / relevant_predicted) if relevant_predicted else 0,
        recall=(true_positive / relevant_expected) if relevant_expected else 0,
    )
