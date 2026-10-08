"""Issue 1–10 orchestration for the second PlayerVoice vertical slice."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from pydantic import Field

from .aliases import AliasDiscoveryResult
from .collectors.base import (
    AdapterRunResult,
    BaseSourceAdapter,
    RetrievalContext,
    SourceStatus,
    collect_all_pages,
)
from .collectors.bilibili import BilibiliCommentsAdapter
from .collectors.reddit import RedditAdapter
from .collectors.steam import SteamReviewsAdapter
from .corpus import CorpusBuildResult, CorpusBuilder
from .evidence import EvidenceStore
from .facts import FactBundle
from .foundation import FoundationResult, run_foundation_slice
from .insights import InsightBundle, generate_insights, render_insight_report
from .intelligence import annotate_corpus, load_taxonomy, write_annotations_jsonl
from .models import (
    CollectionRun,
    ContractModel,
    EvidenceItem,
    FactRecord,
    GameEntity,
    QueryPlan,
    SourceRunStatus,
)
from .query_builder import QueryBuilderSettings, build_query_plans, default_query_languages
from .relevance import evaluate_relevance


AdapterFactory = Callable[[str, GameEntity, QueryPlan, dict[str, Any]], BaseSourceAdapter]


class SourceExecutionSummary(ContractModel):
    source: str
    generated_queries: int = Field(ge=0)
    attempted_queries: int = Field(ge=0)
    successful_queries: int = Field(ge=0)
    failed_queries: int = Field(ge=0)
    raw_items: int = Field(ge=0)
    excluded: dict[str, int]
    statuses: dict[str, int]
    errors: list[str]


class VoiceSliceResult(ContractModel):
    input_name: str
    run_id: str
    foundation: FoundationResult
    query_plans: list[QueryPlan]
    source_execution: dict[str, SourceExecutionSummary]
    raw_community_items: int = Field(ge=0)
    relevance_counts: dict[str, int]
    corpus: CorpusBuildResult
    annotation_count: int = Field(ge=0)
    annotations_path: str | None = None
    insights: InsightBundle
    evidence_store_path: str
    report_path: str
    warnings: list[str]


def _default_adapter_factory(
    source: str,
    game: GameEntity,
    plan: QueryPlan,
    config: dict[str, Any],
) -> BaseSourceAdapter:
    if source == "steam":
        return SteamReviewsAdapter(
            {
                **config,
                "app_id": game.external_ids.get("steam_app_id"),
                "language": "schinese" if plan.language.casefold().startswith("zh") else "english",
            }
        )
    if source == "bilibili":
        return BilibiliCommentsAdapter({**config, "query": plan.query_text})
    if source == "reddit":
        return RedditAdapter(config, game_title=game.canonical_title)
    raise ValueError(f"no community adapter configured for {source}")


def _select_plans(plans: Iterable[QueryPlan], cap_per_source: int) -> list[QueryPlan]:
    grouped: dict[str, list[QueryPlan]] = defaultdict(list)
    for plan in plans:
        grouped[plan.source].append(plan)
    selected: list[QueryPlan] = []
    for source in dict.fromkeys(plan.source for plan in plans):
        candidates = grouped[source]
        chosen: list[QueryPlan] = []
        seen_alias_sets: set[tuple[str, ...]] = set()
        # Preserve at least one auditable plan for each distinct alias route
        # before filling the cap with additional intents/languages.
        for plan in candidates:
            alias_key = tuple(plan.alias_ids)
            if alias_key in seen_alias_sets:
                continue
            seen_alias_sets.add(alias_key)
            chosen.append(plan)
            if len(chosen) >= cap_per_source:
                break
        for plan in candidates:
            if len(chosen) >= cap_per_source:
                break
            if plan not in chosen:
                chosen.append(plan)
        selected.extend(chosen)
    return selected


def _current_fact_bundle(bundle: FactBundle | None, run_id: str) -> FactBundle:
    if bundle is None:
        return FactBundle(game_id="game_unavailable", facts=[], evidence=[], warnings=["fact bundle unavailable"])
    evidence: list[EvidenceItem] = []
    for item in bundle.evidence:
        evidence.append(
            item.model_copy(
                update={
                    "run_id": run_id,
                    "query_id": None,
                    "matched_alias_ids": [],
                    "source_metadata": {
                        **item.source_metadata,
                        "fact_snapshot_reused": item.run_id != run_id,
                        "original_fact_run_id": item.run_id,
                    },
                }
            )
        )
    return bundle.model_copy(update={"evidence": evidence})


def _aggregate_source_runs(
    generated_plans: list[QueryPlan],
    results: dict[str, list[AdapterRunResult]],
) -> tuple[dict[str, SourceExecutionSummary], dict[str, SourceRunStatus], dict[str, dict[str, int]]]:
    execution: dict[str, SourceExecutionSummary] = {}
    statuses: dict[str, SourceRunStatus] = {}
    exclusions: dict[str, dict[str, int]] = {}
    sources = sorted({plan.source for plan in generated_plans}.union(results))
    for source in sources:
        source_results = results.get(source, [])
        status_counts = Counter(result.status.value for result in source_results)
        excluded = Counter()
        errors: list[str] = []
        for result in source_results:
            excluded.update(result.excluded_counts)
            if result.reason:
                errors.append(result.reason)
        raw_items = sum(len(result.items) for result in source_results)
        successful = sum(result.status in {SourceStatus.COLLECTED, SourceStatus.PARTIAL} for result in source_results)
        failed = len(source_results) - successful
        generated = sum(plan.source == source for plan in generated_plans)
        execution[source] = SourceExecutionSummary(
            source=source,
            generated_queries=generated,
            attempted_queries=len(source_results),
            successful_queries=successful,
            failed_queries=failed,
            raw_items=raw_items,
            excluded=dict(excluded),
            statuses=dict(status_counts),
            errors=errors,
        )
        if not source_results:
            state = "disabled"
        elif raw_items and failed:
            state = "partial"
        elif all(result.status == SourceStatus.COLLECTED for result in source_results):
            state = "collected"
        elif any(result.status == SourceStatus.PARTIAL for result in source_results):
            state = "partial"
        elif all(result.status == SourceStatus.UNAVAILABLE for result in source_results):
            state = "unavailable"
        else:
            state = "failed"
        statuses[source] = SourceRunStatus(
            status=state,
            queries_attempted=len(source_results),
            items_retrieved=raw_items,
            duplicates=0,
            error_code=(source_results[0].error_code if failed and source_results else None),
            reason=("; ".join(dict.fromkeys(errors)) or None),
        )
        exclusions[source] = dict(excluded)
    return execution, statuses, exclusions


def run_voice_slice(
    name: str,
    output_root: Path,
    *,
    foundation: FoundationResult | None = None,
    sources: Iterable[str] = ("steam", "bilibili", "reddit"),
    intents: Iterable[str] = ("general", "performance", "bugs", "update"),
    max_plans_per_source: int = 4,
    source_config: dict[str, dict[str, Any]] | None = None,
    adapter_factory: AdapterFactory | None = None,
    run_id: str | None = None,
) -> VoiceSliceResult:
    """Run Query Plan → evidence → relevance → corpus → annotation → insight.

    Supplying a previously validated ``FoundationResult`` is an explicit offline
    fallback; no identity, alias, fact, or community content is fabricated.
    """

    run_id = run_id or f"run_voice_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    foundation = foundation or run_foundation_slice(name, run_id=run_id)
    if foundation.resolution.status.value != "resolved" or foundation.resolution.game is None:
        raise ValueError("voice slice requires a safely resolved canonical game")
    if foundation.aliases is None:
        raise ValueError("voice slice requires validated aliases")
    game = foundation.resolution.game
    aliases: AliasDiscoveryResult = foundation.aliases
    sources = list(sources)
    intents = list(intents)
    languages = default_query_languages(game) or [foundation.resolution.locale]
    settings = QueryBuilderSettings(
        languages=languages,
        sources=sources,
        intents=intents,
        max_per_source_intent=3,
    )
    generated_plans = build_query_plans(game, aliases, run_id=run_id, settings=settings)
    plans = _select_plans(generated_plans, max_plans_per_source)
    factory = adapter_factory or _default_adapter_factory
    config = source_config or {}
    source_results: dict[str, list[AdapterRunResult]] = defaultdict(list)
    raw_items: list[EvidenceItem] = []
    warnings = list(foundation.stage_warnings)
    for plan in plans:
        try:
            adapter = factory(plan.source, game, plan, config.get(plan.source, {}))
            context = RetrievalContext(
                original_game_input=name,
                game_id=game.game_id,
                canonical_title=game.canonical_title,
                run_id=run_id,
                query_plan=plan,
            )
            result = collect_all_pages(adapter, plan, context)
        except Exception as exc:
            result = AdapterRunResult(
                source=plan.source,
                status=SourceStatus.FAILED,
                items=[],
                queries_attempted=1,
                requests_made=0,
                pages_retrieved=0,
                excluded_counts={},
                cursors=[],
                error_code=type(exc).__name__,
                reason=str(exc),
            )
        source_results[plan.source].append(result)
        raw_items.extend(result.items)
    execution, source_status, source_exclusions = _aggregate_source_runs(plans, source_results)

    fact_bundle = _current_fact_bundle(foundation.fact_bundle, run_id)
    if fact_bundle.game_id != game.game_id:
        fact_bundle = FactBundle(game_id=game.game_id, facts=[], evidence=[], warnings=fact_bundle.warnings)
    source_status["official"] = SourceRunStatus(
        status="collected" if fact_bundle.evidence else "unavailable",
        queries_attempted=1,
        items_retrieved=len(fact_bundle.evidence),
        items_relevant=len(fact_bundle.evidence),
        reason=None if fact_bundle.evidence else "no Fact Layer evidence available",
    )
    warnings.extend(fact_bundle.warnings)

    evaluated_items = [
        evaluate_relevance(item, game, aliases.aliases).evidence
        for item in raw_items
    ]
    relevance_counts = dict(sorted(Counter(item.relevance_label.value for item in evaluated_items).items()))
    collection_run = CollectionRun(
        run_id=run_id,
        request_hash=hashlib_sha256(
            {
                "input": name,
                "game_id": game.game_id,
                "sources": sources,
                "intents": intents,
            }
        ),
        game_ids=[game.game_id],
        query_plans=plans,
        code_version="0.4",
        config_version="voice-slice-v1",
        taxonomy_version=load_taxonomy().version,
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
        source_status=source_status,
    )
    output_root.mkdir(parents=True, exist_ok=True)
    store_path = output_root / "evidence.sqlite3"
    store = EvidenceStore(store_path)
    builder = CorpusBuilder(store, output_root / "raw")
    corpus_result = builder.build(
        collection_run,
        [*evaluated_items, *fact_bundle.evidence],
        facts=fact_bundle.facts,
    )
    corpus = builder.default_public_corpus(game.game_id)
    annotations = annotate_corpus(corpus, game)
    annotations_path = output_root / "annotations.jsonl"
    write_annotations_jsonl(annotations, annotations_path)
    all_stored_evidence = store.query_public(game_id=game.game_id)
    insight_bundle = generate_insights(
        game.game_id,
        all_stored_evidence,
        annotations,
        fact_bundle.facts,
        corpus_result.run,
        source_exclusions=source_exclusions,
    )
    report_path = render_insight_report(insight_bundle, store, output_root / "evidence_report.md")
    return VoiceSliceResult(
        input_name=name,
        run_id=run_id,
        foundation=foundation,
        query_plans=plans,
        source_execution=execution,
        raw_community_items=len(raw_items),
        relevance_counts=relevance_counts,
        corpus=corpus_result,
        annotation_count=len(annotations),
        annotations_path=str(annotations_path),
        insights=insight_bundle,
        evidence_store_path=str(store_path),
        report_path=str(report_path),
        warnings=warnings,
    )


def hashlib_sha256(value: Any) -> str:
    import hashlib
    import json

    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
