"""Generate multilingual, source-aware QueryPlan records without network I/O."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml
from pydantic import Field

from .aliases import AliasDiscoveryResult, normalize_alias
from .models import (
    AliasValidationStatus,
    ContractModel,
    ExpectedEvidenceKind,
    GameAlias,
    GameEntity,
    QueryIntent,
    QueryPlan,
)


DEFAULT_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "config/query_templates.yaml"
DEFAULT_SOURCES = ["official", "steam", "reddit", "bilibili"]


class QueryBuilderSettings(ContractModel):
    languages: list[str] = Field(default_factory=lambda: ["zh-CN", "en"])
    sources: list[str] = Field(default_factory=lambda: list(DEFAULT_SOURCES))
    intents: list[QueryIntent] = Field(default_factory=lambda: [QueryIntent.GENERAL])
    max_per_source_intent: int = Field(default=3, ge=1, le=20)


def default_query_languages(game: GameEntity) -> list[str]:
    """Collapse equivalent locale variants into one query language per family."""

    keys = list(game.localized_titles)
    languages: list[str] = []
    if any(key.casefold().startswith("zh") for key in keys):
        languages.append("zh-CN")
    if any(key.casefold().split("-")[0] == "en" for key in keys):
        languages.append("en")
    represented = {"zh" if value.casefold().startswith("zh") else value.casefold().split("-")[0] for value in languages}
    for key in keys:
        family = "zh" if key.casefold().startswith("zh") else key.casefold().split("-")[0]
        if family not in represented:
            languages.append(key)
            represented.add(family)
    return languages


def load_query_templates(path: Path = DEFAULT_TEMPLATE_PATH) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not payload.get("sources") or not payload.get("intent_terms"):
        raise ValueError("query template config must define sources and intent_terms")
    return payload


def _language_family(language: str) -> str:
    return "zh" if language.casefold().startswith("zh") else "en"


def _query_id(run_id: str, source: str, language: str, intent: QueryIntent, query_text: str) -> str:
    value = f"{run_id}|{source}|{language}|{intent.value}|{_semantic_text(query_text)}"
    return f"query_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:20]}"


def _semantic_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def _candidate_aliases(aliases: AliasDiscoveryResult, language: str, game: GameEntity) -> list[GameAlias]:
    family = _language_family(language)
    localized_for_family = {
        normalize_alias(title)
        for title_language, title in game.localized_titles.items()
        if _language_family(title_language) == family
    }
    candidates = [
        alias
        for alias in aliases.aliases
        if alias.search_enabled
        and alias.validation_status in {AliasValidationStatus.VALIDATED, AliasValidationStatus.SCOPED_ONLY}
        and (
            alias.language is None
            or _language_family(alias.language) == family
            or alias.normalized_text in localized_for_family
        )
    ]
    type_order = {
        "official_title": 0,
        "localized_title": 1,
        "abbreviation": 2,
        "transliteration": 3,
        "community_nickname": 4,
        "common_misspelling": 5,
    }
    ordered = sorted(
        candidates,
        key=lambda alias: (
            0 if alias.standalone_search_safe else 1,
            type_order[alias.alias_type.value],
            -alias.confidence,
            alias.normalized_text,
            alias.alias_id,
        ),
    )
    unique: list[GameAlias] = []
    seen_normalized: set[str] = set()
    for alias in ordered:
        if alias.normalized_text in seen_normalized:
            continue
        seen_normalized.add(alias.normalized_text)
        unique.append(alias)
    return unique


def _disambiguators(alias: GameAlias, game: GameEntity) -> list[str]:
    if alias.standalone_search_safe:
        return []
    values = [game.canonical_title]
    if game.developers:
        values.append(game.developers[0])
    if game.platforms:
        values.append(game.platforms[0])
    unique: list[str] = []
    for value in values:
        if normalize_alias(value) != alias.normalized_text and value not in unique:
            unique.append(value)
    return unique


def _expected_kind(source: str, intent: QueryIntent, source_config: dict[str, Any]) -> ExpectedEvidenceKind:
    if source == "official" and intent in {QueryIntent.PATCH, QueryIntent.UPDATE}:
        return ExpectedEvidenceKind(source_config.get("expected_patch", "patch_note"))
    return ExpectedEvidenceKind(source_config["expected_default"])


def _render_query(
    *,
    source: str,
    source_config: dict[str, Any],
    language: str,
    intent: QueryIntent,
    alias: GameAlias,
    game: GameEntity,
    term: str,
    disambiguators: list[str],
) -> str:
    if source == "steam" and game.external_ids.get("steam_app_id"):
        return source_config["identity_template"].format(
            steam_app_id=game.external_ids["steam_app_id"], intent=intent.value,
        )
    template_key = "template_en" if source == "official" and _language_family(language) == "en" else "template"
    template = source_config.get(template_key) or source_config.get("fallback_template")
    if not template:
        raise ValueError(f"source {source!r} has no query template")
    query = template.format(alias=alias.text, term=term, intent=intent.value).strip()
    if disambiguators:
        query = f"{query} {' '.join(disambiguators)}"
    return re.sub(r"\s+", " ", query).strip()


def build_query_plans(
    game: GameEntity,
    aliases: AliasDiscoveryResult,
    *,
    run_id: str,
    settings: QueryBuilderSettings | None = None,
    templates: dict[str, Any] | None = None,
    generated_at: datetime | None = None,
) -> list[QueryPlan]:
    """Create a deterministic, capped query matrix; never execute the plans."""

    if aliases.game_id != game.game_id:
        raise ValueError("alias set does not belong to the requested game")
    settings = settings or QueryBuilderSettings()
    templates = templates or load_query_templates()
    generated_at = generated_at or datetime.now(timezone.utc)
    plans: list[QueryPlan] = []
    seen: set[tuple[str, str, str, str]] = set()

    for source in settings.sources:
        if source not in templates["sources"]:
            raise ValueError(f"unsupported query source: {source}")
        source_config = templates["sources"][source]
        for language in settings.languages:
            candidates = _candidate_aliases(aliases, language, game)
            if not candidates:
                continue
            for intent in settings.intents:
                family = _language_family(language)
                term = templates["intent_terms"][family][intent.value]
                emitted = 0
                for alias in candidates:
                    disambiguators = _disambiguators(alias, game)
                    if not alias.standalone_search_safe and not disambiguators:
                        continue
                    query_text = _render_query(
                        source=source,
                        source_config=source_config,
                        language=language,
                        intent=intent,
                        alias=alias,
                        game=game,
                        term=term,
                        disambiguators=disambiguators,
                    )
                    key = (source, language.casefold(), intent.value, _semantic_text(query_text))
                    if key in seen:
                        continue
                    seen.add(key)
                    plans.append(
                        QueryPlan(
                            query_id=_query_id(run_id, source, language, intent, query_text),
                            run_id=run_id,
                            game_id=game.game_id,
                            source=source,
                            language=language,
                            intent=intent,
                            query_text=query_text,
                            alias_ids=[alias.alias_id],
                            disambiguators=disambiguators,
                            expected_evidence_kind=_expected_kind(source, intent, source_config),
                            generated_at=generated_at,
                        )
                    )
                    emitted += 1
                    if emitted >= settings.max_per_source_intent:
                        break
    return plans
