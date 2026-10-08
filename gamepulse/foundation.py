"""Issue 1–5 vertical slice orchestration; intentionally stops before UGC retrieval."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from pydantic import Field

from .aliases import (
    AliasDiscoveryResult,
    AliasObservation,
    AliasObservationProvider,
    SteamAliasObservationProvider,
    discover_aliases,
)
from .facts import FactAdapter, FactBundle, SteamStoreFactAdapter, collect_fact_layer
from .models import ContractModel, QueryPlan
from .query_builder import QueryBuilderSettings, build_query_plans, default_query_languages
from .resolver import ResolutionResult, ResolverCache, ResolverProvider, resolve_game


class FoundationResult(ContractModel):
    input_name: str
    run_id: str
    resolution: ResolutionResult
    aliases: AliasDiscoveryResult | None
    query_plans: list[QueryPlan]
    fact_bundle: FactBundle | None
    stage_warnings: list[str] = Field(default_factory=list)


def run_foundation_slice(
    name: str,
    *,
    locale: str | None = None,
    run_id: str | None = None,
    resolver_providers: list[ResolverProvider] | None = None,
    resolver_cache: ResolverCache | None = None,
    alias_providers: Iterable[AliasObservationProvider] | None = None,
    alias_observations: Iterable[AliasObservation] = (),
    query_settings: QueryBuilderSettings | None = None,
    fact_adapters: Iterable[FactAdapter] | None = None,
) -> FoundationResult:
    """Run Game Name → Resolver → Alias → Query → Fact with graceful stage failures."""

    run_id = run_id or f"run_foundation_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    resolution = resolve_game(
        name,
        locale=locale,
        providers=resolver_providers,
        cache=resolver_cache,
    )
    if resolution.status.value != "resolved" or resolution.game is None:
        return FoundationResult(
            input_name=name,
            run_id=run_id,
            resolution=resolution,
            aliases=None,
            query_plans=[],
            fact_bundle=None,
            stage_warnings=["pipeline stopped because canonical game resolution was not safe"],
        )

    game = resolution.game
    observations = list(alias_observations)
    warnings: list[str] = []
    providers = list(alias_providers) if alias_providers is not None else [SteamAliasObservationProvider()]
    for provider in providers:
        try:
            observations.extend(provider.discover(game))
        except Exception as exc:
            warnings.append(f"alias provider {provider.name} unavailable: {type(exc).__name__}: {exc}")
    aliases = discover_aliases(game, observations)
    settings = query_settings or QueryBuilderSettings(
        languages=default_query_languages(game) or [resolution.locale],
        sources=["official", "steam", "reddit", "bilibili"],
        intents=["general", "performance", "controls", "patch"],
        max_per_source_intent=3,
    )
    plans = build_query_plans(game, aliases, run_id=run_id, settings=settings)

    adapters = list(fact_adapters) if fact_adapters is not None else [SteamStoreFactAdapter()]
    try:
        facts = collect_fact_layer(game, adapters, run_id=run_id)
    except Exception as exc:
        warning = f"fact layer unavailable: {type(exc).__name__}: {exc}"
        warnings.append(warning)
        facts = FactBundle(game_id=game.game_id, facts=[], evidence=[], warnings=[warning])
    return FoundationResult(
        input_name=name,
        run_id=run_id,
        resolution=resolution,
        aliases=aliases,
        query_plans=plans,
        fact_bundle=facts,
        stage_warnings=warnings,
    )
