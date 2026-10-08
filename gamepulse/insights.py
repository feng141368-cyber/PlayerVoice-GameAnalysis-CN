"""Evidence-linked insight aggregation and truthful coverage reporting."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from pydantic import AwareDatetime, Field

from .evidence import COMMUNITY_KINDS, EvidenceStore
from .intelligence import TaxonomyDefinition, load_taxonomy, priority_eligible_topic
from .models import (
    AnalysisAnnotation,
    CollectionRun,
    ContractModel,
    EvidenceItem,
    FactRecord,
    Insight,
    RelevanceLabel,
    SentimentLabel,
)


INSIGHT_ENGINE_VERSION = "insight-engine-v1"
DECISION_SUPPORT_DISCLAIMER = (
    "Triage decision support from observed evidence volume, negative share, momentum, "
    "and source breadth; not a causal effect or population-prevalence estimate."
)


class InsightSettings(ContractModel):
    min_topic_evidence: int = Field(default=1, ge=1)
    max_topics: int = Field(default=12, ge=1, le=50)
    max_insights_per_type: int = Field(default=12, ge=1, le=50)
    recent_window_days: int = Field(default=30, ge=1, le=365)


class SourceCoverage(ContractModel):
    source: str
    status: str
    queries_attempted: int = Field(ge=0)
    items_retrieved: int = Field(ge=0)
    items_relevant: int = Field(ge=0)
    items_ambiguous: int = Field(ge=0)
    items_irrelevant: int = Field(ge=0)
    duplicates: int = Field(ge=0)
    date_start: AwareDatetime | None = None
    date_end: AwareDatetime | None = None
    languages: dict[str, int] = Field(default_factory=dict)
    exclusions: dict[str, int] = Field(default_factory=dict)
    error_code: str | None = None
    reason: str | None = None


class CoverageReport(ContractModel):
    game_id: str
    run_id: str
    sources: list[SourceCoverage]
    total_evidence: int = Field(ge=0)
    relevant_corpus_size: int = Field(ge=0)
    languages: dict[str, int]
    date_start: AwareDatetime | None = None
    date_end: AwareDatetime | None = None
    excluded_from_analysis: dict[str, int]
    generated_at: AwareDatetime


class InsightBundle(ContractModel):
    game_id: str
    run_id: str
    layer: str = "player_evidence"
    engine_version: str = INSIGHT_ENGINE_VERSION
    player_insights: list[Insight]
    facts: list[FactRecord]
    coverage: CoverageReport
    annotation_count: int = Field(ge=0)
    generated_at: AwareDatetime


def _stable_insight_id(insight_type: str, topic: str, evidence_ids: Iterable[str]) -> str:
    payload = json.dumps(
        [insight_type, topic, sorted(set(evidence_ids))],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"insight_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:20]}"


def _evidence_dates(items: Iterable[EvidenceItem]) -> tuple[datetime | None, datetime | None]:
    values = sorted(item.published_at for item in items if item.published_at is not None)
    return (values[0], values[-1]) if values else (None, None)


def _languages(items: Iterable[EvidenceItem]) -> dict[str, int]:
    counts = Counter(item.language or "unknown" for item in items)
    return dict(sorted(counts.items()))


def build_coverage_report(
    game_id: str,
    run: CollectionRun,
    evidence: Iterable[EvidenceItem],
    *,
    source_exclusions: dict[str, dict[str, int]] | None = None,
    generated_at: datetime | None = None,
) -> CoverageReport:
    generated_at = generated_at or datetime.now(timezone.utc)
    items = [item for item in evidence if item.game_id == game_id]
    by_source: dict[str, list[EvidenceItem]] = defaultdict(list)
    for item in items:
        # Preserve the platform source on the EvidenceItem itself while showing
        # Fact Layer collection separately from community-source retrieval.
        coverage_source = "official" if item.evidence_kind.value == "fact_source" else item.source
        by_source[coverage_source].append(item)
    sources: list[SourceCoverage] = []
    for source in sorted(set(run.source_status).union(by_source)):
        status = run.source_status.get(source)
        source_items = by_source.get(source, [])
        start, end = _evidence_dates(source_items)
        label_counts = Counter(item.relevance_label.value for item in source_items)
        sources.append(
            SourceCoverage(
                source=source,
                status=status.status.value if status else "collected",
                queries_attempted=status.queries_attempted if status else 0,
                items_retrieved=status.items_retrieved if status else len(source_items),
                items_relevant=status.items_relevant if status else label_counts["relevant"],
                items_ambiguous=status.items_ambiguous if status else label_counts["ambiguous"],
                items_irrelevant=status.items_irrelevant if status else label_counts["irrelevant"],
                duplicates=status.duplicates if status else 0,
                date_start=start,
                date_end=end,
                languages=_languages(source_items),
                exclusions=(source_exclusions or {}).get(source, {}),
                error_code=status.error_code if status else None,
                reason=status.reason if status else None,
            )
        )
    overall_start, overall_end = _evidence_dates(items)
    excluded = Counter(item.relevance_label.value for item in items if item.relevance_label != RelevanceLabel.RELEVANT)
    for source_counts in (source_exclusions or {}).values():
        for reason, count in source_counts.items():
            excluded[f"retrieval:{reason}"] += count
    return CoverageReport(
        game_id=game_id,
        run_id=run.run_id,
        sources=sources,
        total_evidence=len(items),
        relevant_corpus_size=sum(
            item.relevance_label == RelevanceLabel.RELEVANT
            and item.evidence_kind.value in COMMUNITY_KINDS
            for item in items
        ),
        languages=_languages(items),
        date_start=overall_start,
        date_end=overall_end,
        excluded_from_analysis=dict(sorted(excluded.items())),
        generated_at=generated_at,
    )


def _sentiment_position(item: EvidenceItem, annotation: AnalysisAnnotation) -> tuple[str, str]:
    if item.recommended is True:
        return "positive", "source_native_recommendation"
    if item.recommended is False:
        return "negative", "source_native_recommendation"
    if annotation.sentiment_label == SentimentLabel.POSITIVE:
        return "positive", "inferred_bilingual_lexicon"
    if annotation.sentiment_label == SentimentLabel.NEGATIVE:
        return "negative", "inferred_bilingual_lexicon"
    if annotation.sentiment_label == SentimentLabel.MIXED:
        return "mixed", "inferred_bilingual_lexicon"
    if annotation.sentiment_label == SentimentLabel.NEUTRAL:
        return "neutral", "inferred_bilingual_lexicon"
    return "unknown", "inferred_bilingual_lexicon"


def _sample_scope(
    items: list[EvidenceItem],
    annotations: dict[str, AnalysisAnnotation],
) -> dict[str, Any]:
    start, end = _evidence_dates(items)
    methods = Counter()
    sentiments = Counter()
    for item in items:
        annotation = annotations[item.evidence_id]
        position, method = _sentiment_position(item, annotation)
        methods[method] += 1
        sentiments[position] += 1
    return {
        "evidence_count": len(items),
        "sources": dict(sorted(Counter(item.source for item in items).items())),
        "languages": _languages(items),
        "date_start": start.isoformat() if start else None,
        "date_end": end.isoformat() if end else None,
        "sentiment_positions": dict(sorted(sentiments.items())),
        "sentiment_methods": dict(sorted(methods.items())),
        "filters": {"relevance": "relevant", "access_scope": "public"},
    }


def _priority(
    topic_items: list[EvidenceItem],
    annotations: dict[str, AnalysisAnnotation],
    coverage: CoverageReport,
    *,
    recent_window_days: int,
) -> dict[str, Any]:
    negative = sum(_sentiment_position(item, annotations[item.evidence_id])[0] == "negative" for item in topic_items)
    negative_share = negative / len(topic_items) if topic_items else 0
    volume_score = min(3, int(math.ceil(math.log2(len(topic_items) + 1)))) if topic_items else 0
    negativity_score = 3 if negative_share >= 0.6 else 2 if negative_share >= 0.4 else 1 if negative_share >= 0.2 else 0
    dated = [item for item in topic_items if item.published_at]
    momentum: float | None = None
    momentum_score = 0
    if dated:
        anchor = max(item.published_at for item in dated if item.published_at)
        recent_start = anchor - timedelta(days=recent_window_days)
        prior_start = recent_start - timedelta(days=recent_window_days)
        recent = sum(item.published_at >= recent_start for item in dated if item.published_at)
        prior = sum(prior_start <= item.published_at < recent_start for item in dated if item.published_at)
        if recent + prior >= 3:
            momentum = round((recent + 0.5) / (prior + 0.5), 3)
            momentum_score = 3 if momentum >= 2 else 2 if momentum >= 1.3 else 1 if momentum >= 1.05 else 0
    eligible_sources = {
        value.source for value in coverage.sources if value.status in {"collected", "partial"}
    }
    represented = {item.source for item in topic_items}.intersection(eligible_sources)
    breadth_score = min(3, len(represented))
    total = volume_score + negativity_score + momentum_score + breadth_score
    label = "high" if total >= 9 else "medium" if total >= 5 else "low"
    return {
        "label": label,
        "components": {
            "volume": {"count": len(topic_items), "score_0_to_3": volume_score},
            "negative_share": {"value": round(negative_share, 4), "score_0_to_3": negativity_score},
            "momentum": {"value": momentum, "score_0_to_3": momentum_score, "window_days": recent_window_days},
            "source_breadth": {
                "represented_collected_sources": sorted(represented),
                "eligible_collected_sources": sorted(eligible_sources),
                "score_0_to_3": breadth_score,
            },
        },
        "total_0_to_12": total,
        "disclaimer": DECISION_SUPPORT_DISCLAIMER,
    }


def _confidence(items: list[EvidenceItem]) -> float:
    breadth = len({item.source for item in items})
    return round(min(0.95, 0.45 + 0.08 * min(len(items), 5) + 0.05 * min(breadth, 2)), 3)


def _make_insight(
    *,
    game_id: str,
    insight_type: str,
    topic: str,
    statement: str,
    supporting: list[EvidenceItem],
    challenging: list[EvidenceItem],
    annotations: dict[str, AnalysisAnnotation],
    generated_at: datetime,
    uncertainty: list[str],
    priority: dict[str, Any] | None = None,
    opportunity_origin: str | None = None,
) -> Insight:
    all_items = list({item.evidence_id: item for item in [*supporting, *challenging]}.values())
    return Insight(
        insight_id=_stable_insight_id(insight_type, topic, [item.evidence_id for item in all_items]),
        scope_type="game",
        scope_ids=[game_id],
        mode="analyst",
        insight_type=insight_type,
        statement=statement,
        taxonomy_nodes=[topic] if topic else [],
        confidence=_confidence(all_items),
        supporting_evidence_ids=[item.evidence_id for item in supporting],
        challenging_evidence_ids=[item.evidence_id for item in challenging],
        context_evidence_ids=[],
        sample_scope=_sample_scope(all_items, annotations),
        uncertainty=uncertainty,
        priority=priority,
        opportunity_origin=opportunity_origin,
        generated_at=generated_at,
    )


def generate_insights(
    game_id: str,
    evidence: Iterable[EvidenceItem],
    annotations: Iterable[AnalysisAnnotation],
    facts: Iterable[FactRecord],
    run: CollectionRun,
    *,
    taxonomy: TaxonomyDefinition | None = None,
    settings: InsightSettings | None = None,
    source_exclusions: dict[str, dict[str, int]] | None = None,
    generated_at: datetime | None = None,
) -> InsightBundle:
    taxonomy = taxonomy or load_taxonomy()
    settings = settings or InsightSettings()
    generated_at = generated_at or datetime.now(timezone.utc)
    all_evidence = [item for item in evidence if item.game_id == game_id]
    corpus = [
        item for item in all_evidence
        if item.access_scope.value == "public" and item.relevance_label == RelevanceLabel.RELEVANT
        and item.evidence_kind.value in COMMUNITY_KINDS
    ]
    annotation_map = {item.evidence_id: item for item in annotations}
    missing = sorted(item.evidence_id for item in corpus if item.evidence_id not in annotation_map)
    if missing:
        raise ValueError(f"relevant evidence is missing annotations: {', '.join(missing[:5])}")
    coverage = build_coverage_report(
        game_id,
        run,
        all_evidence,
        source_exclusions=source_exclusions,
        generated_at=generated_at,
    )
    topic_items: dict[str, list[EvidenceItem]] = defaultdict(list)
    for item in corpus:
        annotation = annotation_map[item.evidence_id]
        for topic in [annotation.primary_topic, *annotation.secondary_topics]:
            if topic:
                topic_items[topic].append(item)

    ranked_topics = sorted(
        topic_items,
        key=lambda topic: (-len({item.evidence_id for item in topic_items[topic]}), topic),
    )[: settings.max_topics]
    insights: list[Insight] = []
    counts_by_type: Counter[str] = Counter()
    base_uncertainty = [
        "Public community evidence is self-selected and not population-representative.",
        "Sentiment is source-native where available and otherwise inferred by transparent lexical rules.",
    ]
    for topic in ranked_topics:
        unique_items = list({item.evidence_id: item for item in topic_items[topic]}.values())
        if len(unique_items) < settings.min_topic_evidence:
            continue
        if not priority_eligible_topic(topic, taxonomy):
            insights.append(
                _make_insight(
                    game_id=game_id,
                    insight_type="research_gap",
                    topic=topic,
                    statement=f"{len(unique_items)} relevant evidence item(s) remain unclassified and need taxonomy review.",
                    supporting=unique_items,
                    challenging=[],
                    annotations=annotation_map,
                    generated_at=generated_at,
                    uncertainty=["No reliable topic assignment was available."],
                )
            )
            continue
        positions: dict[str, list[EvidenceItem]] = defaultdict(list)
        for item in unique_items:
            position, _method = _sentiment_position(item, annotation_map[item.evidence_id])
            positions[position].append(item)
        topic_priority = _priority(
            unique_items,
            annotation_map,
            coverage,
            recent_window_days=settings.recent_window_days,
        )
        if positions["positive"] and counts_by_type["praise"] < settings.max_insights_per_type:
            insights.append(
                _make_insight(
                    game_id=game_id,
                    insight_type="praise",
                    topic=topic,
                    statement=f"In this collected sample, {len(positions['positive'])} evidence item(s) express positive views about {topic}.",
                    supporting=positions["positive"],
                    challenging=positions["negative"],
                    annotations=annotation_map,
                    generated_at=generated_at,
                    uncertainty=base_uncertainty,
                )
            )
            counts_by_type["praise"] += 1
        if positions["negative"] and counts_by_type["complaint"] < settings.max_insights_per_type:
            insights.append(
                _make_insight(
                    game_id=game_id,
                    insight_type="complaint",
                    topic=topic,
                    statement=f"In this collected sample, {len(positions['negative'])} evidence item(s) report negative experiences related to {topic}.",
                    supporting=positions["negative"],
                    challenging=positions["positive"],
                    annotations=annotation_map,
                    generated_at=generated_at,
                    uncertainty=base_uncertainty,
                    priority=topic_priority,
                )
            )
            counts_by_type["complaint"] += 1
        if positions["positive"] and positions["negative"] and counts_by_type["controversy"] < settings.max_insights_per_type:
            insights.append(
                _make_insight(
                    game_id=game_id,
                    insight_type="controversy",
                    topic=topic,
                    statement=f"The collected evidence contains distinguishable positive and negative positions on {topic}.",
                    supporting=positions["positive"],
                    challenging=positions["negative"],
                    annotations=annotation_map,
                    generated_at=generated_at,
                    uncertainty=[*base_uncertainty, "This indicates disagreement in the sample, not population polarisation."],
                )
            )
            counts_by_type["controversy"] += 1
        elif positions["mixed"] and not (positions["positive"] and positions["negative"]):
            insights.append(
                _make_insight(
                    game_id=game_id,
                    insight_type="research_gap",
                    topic=topic,
                    statement=f"Mixed evidence on {topic} is an open question; the sample lacks two clearly distinguishable positions.",
                    supporting=positions["mixed"],
                    challenging=[],
                    annotations=annotation_map,
                    generated_at=generated_at,
                    uncertainty=["Not enough distinct positive and negative positions for a controversy claim."],
                )
            )

        by_source: dict[str, list[EvidenceItem]] = defaultdict(list)
        for item in unique_items:
            by_source[item.source].append(item)
        if len(by_source) >= 2 and counts_by_type["difference"] < settings.max_insights_per_type:
            shares = {}
            for source, source_items in by_source.items():
                shares[source] = sum(
                    _sentiment_position(item, annotation_map[item.evidence_id])[0] == "negative"
                    for item in source_items
                ) / len(source_items)
            high = max(shares, key=shares.get)
            low = min(shares, key=shares.get)
            if shares[high] - shares[low] >= 0.30:
                insights.append(
                    _make_insight(
                        game_id=game_id,
                        insight_type="difference",
                        topic=topic,
                        statement=f"Negative share for {topic} differs between collected {high} and {low} evidence.",
                        supporting=by_source[high],
                        challenging=by_source[low],
                        annotations=annotation_map,
                        generated_at=generated_at,
                        uncertainty=[*base_uncertainty, "Source audiences and collection methods differ; this is not a market-level comparison."],
                    )
                )
                counts_by_type["difference"] += 1

    request_groups: dict[str, list[EvidenceItem]] = defaultdict(list)
    need_groups: dict[str, list[EvidenceItem]] = defaultdict(list)
    for item in corpus:
        annotation = annotation_map[item.evidence_id]
        for request in annotation.explicit_feature_requests:
            request_groups[request].append(item)
        for need in annotation.underlying_needs:
            need_groups[need].append(item)
    for request, items in sorted(request_groups.items(), key=lambda value: (-len(value[1]), value[0]))[: settings.max_insights_per_type]:
        topic = annotation_map[items[0].evidence_id].primary_topic or "other_unclassified"
        insights.append(
            _make_insight(
                game_id=game_id,
                insight_type="opportunity",
                topic=topic,
                statement=f"Explicit player request in the collected sample: {request}",
                supporting=list({item.evidence_id: item for item in items}.values()),
                challenging=[],
                annotations=annotation_map,
                generated_at=generated_at,
                uncertainty=[*base_uncertainty, "A stated request is not proof that the proposed solution is optimal."],
                priority=_priority(items, annotation_map, coverage, recent_window_days=settings.recent_window_days),
                opportunity_origin="explicit_request",
            )
        )
    for need, items in sorted(need_groups.items(), key=lambda value: (-len(value[1]), value[0]))[: settings.max_insights_per_type]:
        topic = annotation_map[items[0].evidence_id].primary_topic or "other_unclassified"
        insights.append(
            _make_insight(
                game_id=game_id,
                insight_type="opportunity",
                topic=topic,
                statement=f"Inferred opportunity to investigate: {need}.",
                supporting=list({item.evidence_id: item for item in items}.values()),
                challenging=[],
                annotations=annotation_map,
                generated_at=generated_at,
                uncertainty=[*base_uncertainty, "This opportunity is inferred from pain points, not an explicit solution request."],
                priority=_priority(items, annotation_map, coverage, recent_window_days=settings.recent_window_days),
                opportunity_origin="inferred_need",
            )
        )

    return InsightBundle(
        game_id=game_id,
        run_id=run.run_id,
        player_insights=insights,
        facts=[fact for fact in facts if fact.game_id == game_id],
        coverage=coverage,
        annotation_count=len(annotation_map),
        generated_at=generated_at,
    )


def validate_insight_integrity(bundle: InsightBundle, store: EvidenceStore) -> None:
    unresolved: list[str] = []
    for insight in bundle.player_insights:
        for evidence_id in [
            *insight.supporting_evidence_ids,
            *insight.challenging_evidence_ids,
            *insight.context_evidence_ids,
        ]:
            if store.get_evidence(evidence_id) is None:
                unresolved.append(evidence_id)
    for fact in bundle.facts:
        if store.get_evidence(fact.source_evidence_id) is None:
            unresolved.append(fact.source_evidence_id)
    if unresolved:
        raise ValueError(f"unresolved evidence links: {', '.join(sorted(set(unresolved)))}")
    stored_run = store.get_run(bundle.run_id)
    if stored_run is None:
        raise ValueError(f"run manifest {bundle.run_id} is not stored")
    stored_relevant = len(store.query_relevant_ugc(bundle.game_id))
    if stored_relevant != bundle.coverage.relevant_corpus_size:
        raise ValueError(
            f"coverage/store relevant count mismatch: {bundle.coverage.relevant_corpus_size} != {stored_relevant}"
        )


def _markdown_cell(value: Any, *, limit: int = 280) -> str:
    text = " ".join(str(value).split()).replace("|", "\\|")
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def render_insight_report(bundle: InsightBundle, store: EvidenceStore, output: Path) -> Path:
    validate_insight_integrity(bundle, store)
    lines = [
        f"# PlayerVoice evidence report — {bundle.game_id}",
        "",
        f"Generated: {bundle.generated_at.isoformat()}",
        "",
        "## Coverage",
        "",
        "| Source | Status | Retrieved | Relevant | Ambiguous | Irrelevant | Duplicates | Dates | Languages | Exclusions | Reason |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- |",
    ]
    for source in bundle.coverage.sources:
        dates = "—"
        if source.date_start or source.date_end:
            dates = f"{source.date_start.date() if source.date_start else '?'} → {source.date_end.date() if source.date_end else '?'}"
        lines.append(
            f"| {source.source} | {source.status} | {source.items_retrieved} | {source.items_relevant} | "
            f"{source.items_ambiguous} | {source.items_irrelevant} | {source.duplicates} | {dates} | "
            f"{json.dumps(source.languages, ensure_ascii=False)} | "
            f"{_markdown_cell(json.dumps(source.exclusions, ensure_ascii=False))} | "
            f"{_markdown_cell(source.reason or '')} |"
        )
    lines.extend(["", "## Official facts (Fact Layer)", ""])
    if bundle.facts:
        lines.extend(["| Fact | Value | Scope | Evidence |", "| --- | --- | --- | --- |"])
        for fact in bundle.facts:
            value = json.dumps(fact.value, ensure_ascii=False) if not isinstance(fact.value, str) else fact.value
            lines.append(
                f"| {fact.fact_type} | {_markdown_cell(value)} | {fact.platform or fact.territory or 'global'} | `{fact.source_evidence_id}` |"
            )
    else:
        lines.append("No Fact Layer records were available for this run.")
    lines.extend(["", "## Player insights (Player Evidence Layer)", ""])
    if not bundle.player_insights:
        lines.append("No evidence-bounded player insight met the current rules.")
    for insight in bundle.player_insights:
        lines.extend(
            [
                f"### {insight.insight_type.value}: {', '.join(insight.taxonomy_nodes) or 'general'}",
                "",
                insight.statement,
                "",
                f"- Confidence: {insight.confidence:.2f}",
                f"- Supporting evidence: {', '.join(f'`{value}`' for value in insight.supporting_evidence_ids)}",
                f"- Challenging evidence: {', '.join(f'`{value}`' for value in insight.challenging_evidence_ids) or 'none'}",
                f"- Sample scope: `{json.dumps(insight.sample_scope, ensure_ascii=False, sort_keys=True)}`",
            ]
        )
        if insight.priority:
            lines.append(f"- Priority: `{json.dumps(insight.priority, ensure_ascii=False, sort_keys=True)}`")
        for uncertainty in insight.uncertainty:
            lines.append(f"- Uncertainty: {uncertainty}")
        lines.append("")

    evidence_ids = sorted(
        {
            value
            for insight in bundle.player_insights
            for value in [
                *insight.supporting_evidence_ids,
                *insight.challenging_evidence_ids,
                *insight.context_evidence_ids,
            ]
        }.union({fact.source_evidence_id for fact in bundle.facts})
    )
    lines.extend(
        [
            "## Evidence traceback",
            "",
            "| Evidence ID | Layer | Source | Original source/reference | Excerpt |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    fact_ids = {fact.source_evidence_id for fact in bundle.facts}
    for evidence_id in evidence_ids:
        item = store.get_evidence(evidence_id)
        if item is None:
            continue
        source_reference = item.source_url or item.source_reference or "unavailable"
        if item.source_url:
            source_reference = f"[source]({item.source_url})"
        excerpt = " ".join(item.original_text.split())[:220].replace("|", "\\|")
        layer = "Fact" if evidence_id in fact_ids else "Player Evidence"
        lines.append(f"| `{evidence_id}` | {layer} | {item.source} | {source_reference} | {excerpt} |")
    lines.extend(["", f"> {DECISION_SUPPORT_DISCLAIMER}", ""])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    return output
