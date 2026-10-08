"""Dimension-level Compare Mode over shared Intelligence Core snapshots."""

from __future__ import annotations

from collections import Counter
from typing import Any, Literal

from pydantic import AwareDatetime, Field, model_validator

from ..models import AnalysisAnnotation, ContractModel, EvidenceItem
from .core import IntelligenceCoreSnapshot
from .player import FitDimension, PreferenceProfile, _fit, parse_preference_profile


DEFAULT_COMPARE_DIMENSIONS = [
    "performance",
    "exploration",
    "story",
    "combat",
    "daily_commitment",
    "monetisation",
    "graphics",
    "audio",
    "controls",
    "fair_play_integrity",
    "bugs_stability",
]

DEFAULT_FACT_DIMENSIONS = [
    "platform_support",
    "minimum_requirements",
    "storage_requirement",
    "supported_languages",
    "cross_play",
]


class ComparisonCell(ContractModel):
    game_id: str
    dimension: str
    evidence_count: int = Field(ge=0)
    corpus_share_percent: float = Field(ge=0, le=100)
    source_distribution: dict[str, int]
    language_distribution: dict[str, int]
    sentiment_positions: dict[str, int]
    date_start: AwareDatetime | None = None
    date_end: AwareDatetime | None = None
    confidence: Literal["insufficient", "low", "medium", "higher"]
    insight_ids: list[str]
    evidence_ids: list[str]
    summary: str


class FactComparisonCell(ContractModel):
    game_id: str
    fact_type: str
    status: Literal["available", "insufficient"]
    values: list[Any]
    fact_ids: list[str]
    evidence_ids: list[str]
    platforms: list[str]


class FactDimensionComparison(ContractModel):
    fact_type: str
    status: Literal["comparable", "partial", "insufficient_evidence"]
    reason: str
    cells: list[FactComparisonCell] = Field(min_length=2, max_length=4)


class DimensionComparison(ContractModel):
    dimension: str
    status: Literal["comparable", "comparable_with_caution", "insufficient_evidence"]
    reason: str
    cells: list[ComparisonCell] = Field(min_length=2, max_length=4)

    @model_validator(mode="after")
    def require_one_cell_per_game(self) -> "DimensionComparison":
        ids = [value.game_id for value in self.cells]
        if len(ids) != len(set(ids)):
            raise ValueError("comparison dimension contains duplicate games")
        return self


class GameCoverageSummary(ContractModel):
    game_id: str
    game_title: str
    relevant_corpus_size: int
    sources: dict[str, int]
    languages: dict[str, int]
    date_start: AwareDatetime | None = None
    date_end: AwareDatetime | None = None
    extension_topics: dict[str, int]


class CompareReport(ContractModel):
    game_ids: list[str] = Field(min_length=2, max_length=4)
    taxonomy_version: str
    dimensions: list[DimensionComparison]
    fact_dimensions: list[FactDimensionComparison]
    coverage: list[GameCoverageSummary]
    preference_profile: PreferenceProfile | None = None
    preference_fit: dict[str, list[FitDimension]]
    limitations: list[str]
    no_winner_score: bool = True


def _accepted_topics(dimension: str) -> set[str]:
    if dimension == "audio":
        return {"audio", "audio_music", "audio_sound_design", "audio_voice_acting"}
    return {dimension}


def _position(evidence: EvidenceItem, annotation: AnalysisAnnotation) -> str:
    if evidence.recommended is True:
        return "positive"
    if evidence.recommended is False:
        return "negative"
    return annotation.sentiment_label.value


def _cell(snapshot: IntelligenceCoreSnapshot, dimension: str) -> ComparisonCell:
    accepted = _accepted_topics(dimension)
    evidence_by_id = snapshot.evidence_by_id
    annotations = [
        value
        for value in snapshot.annotations
        if accepted.intersection({value.primary_topic, *value.secondary_topics})
    ]
    items = [evidence_by_id[value.evidence_id] for value in annotations]
    dates = sorted(item.published_at for item in items if item.published_at is not None)
    sources = Counter(item.source for item in items)
    languages = Counter(item.language or "unknown" for item in items)
    positions = Counter(
        _position(item, annotation)
        for item, annotation in zip(items, annotations)
    )
    insights = [
        value
        for value in snapshot.insight_bundle.player_insights
        if accepted.intersection(value.taxonomy_nodes)
    ]
    count = len(items)
    corpus_size = sum(
        1
        for item in snapshot.evidence
        if item.relevance_label.value == "relevant"
        and item.evidence_kind.value
        in {"review", "post", "comment", "video_comment", "forum_thread", "forum_reply"}
    )
    if count == 0:
        confidence = "insufficient"
        summary = "No relevant evidence was classified for this dimension."
    elif count < 3:
        confidence = "low"
        summary = f"Only {count} relevant evidence item(s); treat the observed pattern as limited."
    elif len(sources) >= 2 and count >= 5:
        confidence = "higher"
        summary = f"{count} relevant items across {len(sources)} sources; still a self-selected sample."
    else:
        confidence = "medium"
        summary = f"{count} relevant items from {len(sources)} source(s); source breadth remains limited."
    return ComparisonCell(
        game_id=snapshot.game.game_id,
        dimension=dimension,
        evidence_count=count,
        corpus_share_percent=round((count / corpus_size * 100), 1) if corpus_size else 0.0,
        source_distribution=dict(sorted(sources.items())),
        language_distribution=dict(sorted(languages.items())),
        sentiment_positions=dict(sorted(positions.items())),
        date_start=dates[0] if dates else None,
        date_end=dates[-1] if dates else None,
        confidence=confidence,
        insight_ids=[value.insight_id for value in insights],
        evidence_ids=[item.evidence_id for item in items],
        summary=summary,
    )


def _fact_cell(snapshot: IntelligenceCoreSnapshot, fact_type: str) -> FactComparisonCell:
    facts = [value for value in snapshot.facts if value.fact_type == fact_type]
    return FactComparisonCell(
        game_id=snapshot.game.game_id,
        fact_type=fact_type,
        status="available" if facts else "insufficient",
        values=[value.value for value in facts],
        fact_ids=[value.fact_id for value in facts],
        evidence_ids=sorted({value.source_evidence_id for value in facts}),
        platforms=sorted({value.platform for value in facts if value.platform}),
    )


def _fact_comparison(
    snapshots: list[IntelligenceCoreSnapshot], fact_type: str
) -> FactDimensionComparison:
    cells = [_fact_cell(snapshot, fact_type) for snapshot in snapshots]
    available = sum(value.status == "available" for value in cells)
    if available == len(cells):
        status = "comparable"
        reason = "A verified Fact Layer value is available for every game."
    elif available:
        status = "partial"
        reason = "At least one game lacks this Fact Layer value; only available facts are shown."
    else:
        status = "insufficient_evidence"
        reason = "No game has a verified Fact Layer value for this dimension."
    return FactDimensionComparison(
        fact_type=fact_type,
        status=status,
        reason=reason,
        cells=cells,
    )


def _comparison_status(cells: list[ComparisonCell]) -> tuple[str, str]:
    if any(value.evidence_count < 3 for value in cells):
        return (
            "insufficient_evidence",
            "At least one game has fewer than three relevant items; no reliable cross-game difference is asserted.",
        )
    source_sets = [set(value.source_distribution) for value in cells]
    date_ends = [value.date_end for value in cells if value.date_end]
    materially_different_sources = len({tuple(sorted(value)) for value in source_sets}) > 1
    materially_different_time = False
    if len(date_ends) == len(cells):
        materially_different_time = (max(date_ends) - min(date_ends)).days > 180
    counts = [value.evidence_count for value in cells]
    imbalanced_counts = max(counts) / max(1, min(counts)) > 4
    if materially_different_sources or materially_different_time or imbalanced_counts:
        reasons = []
        if materially_different_sources:
            reasons.append("source mix differs")
        if materially_different_time:
            reasons.append("latest evidence dates differ by more than 180 days")
        if imbalanced_counts:
            reasons.append("sample sizes differ by more than 4×")
        return (
            "comparable_with_caution",
            "; ".join(reasons) + ". Raw counts and coverage must accompany any interpretation.",
        )
    return (
        "comparable",
        "All games meet the minimum evidence floor with broadly aligned source, time, and sample coverage.",
    )


def _coverage(snapshot: IntelligenceCoreSnapshot) -> GameCoverageSummary:
    relevant = [
        item
        for item in snapshot.evidence
        if item.relevance_label.value == "relevant"
        and item.evidence_kind.value in {"review", "post", "comment", "video_comment", "forum_thread", "forum_reply"}
    ]
    dates = sorted(item.published_at for item in relevant if item.published_at)
    extensions = Counter(
        topic
        for annotation in snapshot.annotations
        for topic in [annotation.primary_topic, *annotation.secondary_topics]
        if "." in topic
    )
    return GameCoverageSummary(
        game_id=snapshot.game.game_id,
        game_title=snapshot.game.canonical_title,
        relevant_corpus_size=len(relevant),
        sources=dict(sorted(Counter(item.source for item in relevant).items())),
        languages=dict(sorted(Counter(item.language or "unknown" for item in relevant).items())),
        date_start=dates[0] if dates else None,
        date_end=dates[-1] if dates else None,
        extension_topics=dict(sorted(extensions.items())),
    )


def build_compare_report(
    snapshots: list[IntelligenceCoreSnapshot],
    preferences: str | dict[str, Any] | PreferenceProfile | None = None,
    *,
    dimensions: list[str] | None = None,
    fact_dimensions: list[str] | None = None,
) -> CompareReport:
    if not 2 <= len(snapshots) <= 4:
        raise ValueError("Compare Mode requires two to four Intelligence Core snapshots")
    game_ids = [snapshot.game.game_id for snapshot in snapshots]
    if len(game_ids) != len(set(game_ids)):
        raise ValueError("Compare Mode requires distinct game snapshots")
    versions = {
        annotation.taxonomy_version
        for snapshot in snapshots
        for annotation in snapshot.annotations
    }
    if not versions or len(versions) != 1:
        raise ValueError("Compare Mode requires one shared taxonomy version")
    requested_dimensions = dimensions or DEFAULT_COMPARE_DIMENSIONS
    comparisons = []
    for dimension in requested_dimensions:
        cells = [_cell(snapshot, dimension) for snapshot in snapshots]
        status, reason = _comparison_status(cells)
        comparisons.append(
            DimensionComparison(
                dimension=dimension,
                status=status,
                reason=reason,
                cells=cells,
            )
        )
    profile = parse_preference_profile(preferences) if preferences else None
    return CompareReport(
        game_ids=game_ids,
        taxonomy_version=next(iter(versions)),
        dimensions=comparisons,
        fact_dimensions=[
            _fact_comparison(snapshots, fact_type)
            for fact_type in (fact_dimensions or DEFAULT_FACT_DIMENSIONS)
        ],
        coverage=[_coverage(snapshot) for snapshot in snapshots],
        preference_profile=profile,
        preference_fit=(
            {snapshot.game.game_id: _fit(snapshot, profile) for snapshot in snapshots}
            if profile
            else {}
        ),
        limitations=[
            "Raw evidence counts, source mix, language coverage, recency, and confidence are shown for every dimension.",
            "Corpus share normalises topic coverage within each collected corpus; it is not population prevalence.",
            "Public community samples are self-selected; comparison status is not a market-share or quality ranking.",
            "Missing dimensions remain insufficient and never receive a neutral score or winner.",
        ],
    )


def render_compare_markdown(
    report: CompareReport,
    title_by_game_id: dict[str, str],
) -> str:
    game_titles = [title_by_game_id[value] for value in report.game_ids]
    lines = [
        f"# Compare Mode — {' vs '.join(game_titles)}",
        "",
        f"Shared taxonomy: `{report.taxonomy_version}`",
        "",
        "## Evidence coverage",
        "",
        "| Game | Relevant corpus | Sources | Languages | Date coverage |",
        "| --- | ---: | --- | --- | --- |",
    ]
    for value in report.coverage:
        dates = f"{value.date_start.date() if value.date_start else '?'} → {value.date_end.date() if value.date_end else '?'}"
        lines.append(
            f"| {value.game_title} | {value.relevant_corpus_size} | "
            f"{json_dump(value.sources)} | {json_dump(value.languages)} | {dates} |"
        )
    lines.extend(["", "## Dimension comparison", ""])
    header = "| Dimension | Status | " + " | ".join(game_titles) + " |"
    divider = "| --- | --- | " + " | ".join("---" for _ in game_titles) + " |"
    lines.extend([header, divider])
    for dimension in report.dimensions:
        values = []
        for cell in dimension.cells:
            values.append(
                f"n={cell.evidence_count}; share={cell.corpus_share_percent}%; confidence={cell.confidence}; sources={json_dump(cell.source_distribution)}; sentiment={json_dump(cell.sentiment_positions)}"
            )
        lines.append(
            f"| {dimension.dimension} | {dimension.status}: {dimension.reason} | "
            + " | ".join(values)
            + " |"
        )
    lines.extend(["", "## Verified Fact Layer comparison", ""])
    fact_header = "| Fact | Status | " + " | ".join(game_titles) + " |"
    fact_divider = "| --- | --- | " + " | ".join("---" for _ in game_titles) + " |"
    lines.extend([fact_header, fact_divider])
    for dimension in report.fact_dimensions:
        values = [
            json_dump(cell.values) if cell.status == "available" else "Insufficient verified fact evidence"
            for cell in dimension.cells
        ]
        lines.append(
            f"| {dimension.fact_type} | {dimension.status}: {dimension.reason} | "
            + " | ".join(values)
            + " |"
        )
    if report.preference_profile:
        lines.extend(["", "## Preference-aware considerations", ""])
        for game_id in report.game_ids:
            lines.extend([f"### {title_by_game_id[game_id]}", ""])
            for item in report.preference_fit[game_id]:
                lines.append(f"- **{item.assessment}: {item.dimension}** — {item.rationale}")
            lines.append("")
    lines.extend(["> No winner score is computed. Insufficient or materially different evidence coverage blocks a reliable comparison claim.", ""])
    return "\n".join(lines)


def json_dump(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True)
