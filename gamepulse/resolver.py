"""Canonical game resolution without community alias expansion.

Call :func:`resolve_game` with a free-text title. The result is always typed and is
one of ``resolved``, ``needs_choice`` or ``unresolved``. Providers return official
or platform metadata; candidate selection never relies on string similarity alone.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Protocol

from pydantic import AwareDatetime, Field

from .http import CollectionError, request_json
from .models import ContractModel, GameEntity, ResolutionStatus


JsonRequester = Callable[..., Any]


def normalize_name(value: str) -> str:
    return re.sub(r"[^\w]+", "", value.casefold(), flags=re.UNICODE)


def infer_locale(name: str) -> str:
    return "zh-CN" if any("\u3400" <= char <= "\u9fff" for char in name) else "en"


def _evidence_id(provider: str, provider_id: str) -> str:
    digest = hashlib.sha256(f"{provider}:{provider_id}".encode("utf-8")).hexdigest()[:20]
    return f"ev_resolver_{digest}"


def _stable_game_id(external_ids: dict[str, str], canonical_title: str) -> str:
    if external_ids.get("wikidata_id"):
        return f"game_wikidata_{external_ids['wikidata_id'].casefold()}"
    if external_ids.get("steam_app_id"):
        return f"game_steam_{external_ids['steam_app_id']}"
    digest = hashlib.sha256(normalize_name(canonical_title).encode("utf-8")).hexdigest()[:16]
    return f"game_title_{digest}"


class ResolverEvidence(ContractModel):
    evidence_id: str = Field(pattern=r"^ev_resolver_.+")
    provider: str
    source_reference: str
    source_url: str | None = None
    retrieved_at: AwareDatetime


class ProviderCandidate(ContractModel):
    provider: str
    provider_id: str
    canonical_title: str
    original_title: str | None = None
    localized_titles: dict[str, str]
    external_ids: dict[str, str]
    developers: list[str] = Field(default_factory=list)
    publishers: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    release_dates: dict[str, str] = Field(default_factory=dict)
    genres: list[str] = Field(default_factory=list)
    franchise: str | None = None
    official_urls: list[str] = Field(default_factory=list)
    provider_match_score: float = Field(default=0, ge=0, le=1)
    evidence: ResolverEvidence


class CandidateAssessment(ContractModel):
    entity: GameEntity
    score: float = Field(ge=0, le=1)
    reasons: list[str]
    evidence: list[ResolverEvidence]
    providers: list[str]


class ProviderFailure(ContractModel):
    provider: str
    error_type: str
    reason: str


class ResolutionContext(ContractModel):
    developer: str | None = None
    publisher: str | None = None
    platform: str | None = None
    external_ids: dict[str, str] = Field(default_factory=dict)


class ResolutionResult(ContractModel):
    input_name: str
    locale: str
    status: ResolutionStatus
    game: GameEntity | None
    candidates: list[CandidateAssessment]
    reasons: list[str]
    provider_failures: list[ProviderFailure]
    partial: bool


class ResolverProvider(Protocol):
    name: str

    def search(self, name: str, locale: str) -> list[ProviderCandidate]: ...


class ResolverCache:
    """Small file cache keyed by provider, normalized input, and locale."""

    def __init__(self, root: Path):
        self.root = root

    def _path(self, provider: str, name: str, locale: str) -> Path:
        key = json.dumps([provider, normalize_name(name), locale.casefold()], ensure_ascii=False)
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.root / provider / f"{digest}.json"

    def get(self, provider: str, name: str, locale: str) -> list[ProviderCandidate] | None:
        path = self._path(provider, name, locale)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [ProviderCandidate.model_validate(item) for item in payload]

    def set(self, provider: str, name: str, locale: str, candidates: list[ProviderCandidate]) -> None:
        path = self._path(provider, name, locale)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [item.model_dump(mode="json") for item in candidates]
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class FixtureResolverProvider:
    """Deterministic provider used by tests and offline demonstrations."""

    name = "fixture"

    def __init__(self, path: Path):
        self.path = path
        self.calls = 0

    def search(self, name: str, locale: str) -> list[ProviderCandidate]:
        self.calls += 1
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        key = f"{locale.casefold()}|{normalize_name(name)}"
        return [ProviderCandidate.model_validate(item) for item in payload.get("queries", {}).get(key, [])]


class WikidataResolverProvider:
    name = "wikidata"

    def __init__(self, requester: JsonRequester = request_json):
        self.requester = requester

    @staticmethod
    def _language(locale: str) -> str:
        return "zh" if locale.casefold().startswith("zh") else locale.split("-")[0].casefold()

    def search(self, name: str, locale: str) -> list[ProviderCandidate]:
        language = self._language(locale)
        search = self.requester(
            "https://www.wikidata.org/w/api.php",
            params={
                "action": "wbsearchentities", "search": name, "language": language,
                "uselang": language, "type": "item", "format": "json", "limit": 8,
            },
            headers={"User-Agent": "PlayerVoice/0.3 portfolio research"},
            retries=1,
            timeout=12,
        )
        raw_results = search.get("search") or []
        likely_games = [
            item for item in raw_results
            if any(token in str(item.get("description", "")).casefold() for token in ("game", "游戏", "遊戲"))
        ]
        selected = (likely_games or raw_results)[:5]
        if not selected:
            return []
        ids = "|".join(str(item["id"]) for item in selected)
        response = self.requester(
            "https://www.wikidata.org/w/api.php",
            params={
                "action": "wbgetentities", "ids": ids,
                "props": "labels|aliases|descriptions|sitelinks|claims",
                "languages": "en|zh|zh-cn|zh-hans|zh-hant", "format": "json",
            },
            headers={"User-Agent": "PlayerVoice/0.3 portfolio research"},
            retries=1,
            timeout=12,
        )
        retrieved_at = datetime.now(timezone.utc)
        candidates: list[ProviderCandidate] = []
        for rank, search_item in enumerate(selected):
            entity_id = str(search_item["id"])
            entity = response.get("entities", {}).get(entity_id, {})
            labels = entity.get("labels", {})
            localized = {
                key: value.get("value")
                for key, value in labels.items()
                if value.get("value") and key in {"en", "zh", "zh-cn", "zh-hans", "zh-hant"}
            }
            canonical = localized.get(language) or localized.get("zh-cn") or localized.get("zh") or localized.get("en")
            canonical = canonical or str(search_item.get("label") or name)
            evidence = ResolverEvidence(
                evidence_id=_evidence_id(self.name, entity_id),
                provider=self.name,
                source_reference=entity_id,
                source_url=f"https://www.wikidata.org/wiki/{entity_id}",
                retrieved_at=retrieved_at,
            )
            candidates.append(
                ProviderCandidate(
                    provider=self.name,
                    provider_id=entity_id,
                    canonical_title=canonical,
                    original_title=localized.get("en") or canonical,
                    localized_titles=localized,
                    external_ids={"wikidata_id": entity_id},
                    provider_match_score=max(0.5, 1 - rank * 0.1),
                    evidence=evidence,
                )
            )
        return candidates


class SteamResolverProvider:
    name = "steam"

    def __init__(self, requester: JsonRequester = request_json, country: str = "US"):
        self.requester = requester
        self.country = country

    @staticmethod
    def _language(locale: str) -> str:
        return "schinese" if locale.casefold().startswith("zh") else "english"

    def search(self, name: str, locale: str) -> list[ProviderCandidate]:
        language = self._language(locale)
        country = "CN" if locale.casefold().startswith("zh") else self.country
        response = self.requester(
            "https://store.steampowered.com/api/storesearch/",
            params={"term": name, "l": language, "cc": country},
            headers={"User-Agent": "PlayerVoice/0.3"},
            retries=2,
            timeout=20,
        )
        retrieved_at = datetime.now(timezone.utc)
        candidates: list[ProviderCandidate] = []
        for rank, item in enumerate((response.get("items") or [])[:3]):
            app_id = str(item["id"])
            title = str(item.get("name") or name)
            detail_variants: dict[str, dict[str, Any]] = {}
            if rank == 0:
                detail_languages = list(dict.fromkeys([language, "english", "schinese"]))
                for detail_language in detail_languages:
                    details_payload = self.requester(
                        "https://store.steampowered.com/api/appdetails",
                        params={"appids": app_id, "l": detail_language, "cc": country},
                        headers={"User-Agent": "PlayerVoice/0.3"},
                        retries=2,
                        timeout=20,
                    )
                    detail_variants[detail_language] = (details_payload.get(app_id) or {}).get("data") or {}
            details = detail_variants.get(language) or detail_variants.get("english") or {}
            platform_flags = details.get("platforms") or {}
            platforms = [platform for platform, supported in platform_flags.items() if supported]
            localized_titles: dict[str, str] = {}
            if detail_variants.get("english", {}).get("name"):
                localized_titles["en"] = str(detail_variants["english"]["name"])
            if detail_variants.get("schinese", {}).get("name"):
                localized_titles["zh-CN"] = str(detail_variants["schinese"]["name"])
            requested_key = "zh-CN" if language == "schinese" else "en"
            requested_title = localized_titles.get(requested_key) or str(details.get("name") or title)
            evidence = ResolverEvidence(
                evidence_id=_evidence_id(self.name, app_id), provider=self.name,
                source_reference=f"steam_app:{app_id}",
                source_url=f"https://store.steampowered.com/app/{app_id}/",
                retrieved_at=retrieved_at,
            )
            candidates.append(
                ProviderCandidate(
                    provider=self.name,
                    provider_id=app_id,
                    canonical_title=requested_title,
                    original_title=localized_titles.get("en") or requested_title,
                    localized_titles=localized_titles or {requested_key: requested_title},
                    external_ids={"steam_app_id": app_id},
                    developers=[str(value) for value in details.get("developers") or []],
                    publishers=[str(value) for value in details.get("publishers") or []],
                    platforms=platforms,
                    genres=[str(value.get("description")) for value in details.get("genres") or [] if value.get("description")],
                    official_urls=[str(details["website"])] if details.get("website") else [],
                    provider_match_score=max(0.5, 1 - rank * 0.1),
                    evidence=evidence,
                )
            )
        return candidates


@dataclass
class _MergedCandidate:
    values: list[ProviderCandidate]

    @property
    def titles(self) -> dict[str, str]:
        combined: dict[str, str] = {}
        for value in self.values:
            combined.update(value.localized_titles)
        return combined

    @property
    def normalized_titles(self) -> set[str]:
        titles = [value.canonical_title for value in self.values]
        titles.extend(title for value in self.values for title in value.localized_titles.values())
        return {normalize_name(title) for title in titles if title}

    @property
    def external_ids(self) -> dict[str, str]:
        combined: dict[str, str] = {}
        for value in self.values:
            combined.update(value.external_ids)
        return combined


def _overlaps(left: _MergedCandidate, right: ProviderCandidate) -> bool:
    shared_namespaces = set(left.external_ids) & set(right.external_ids)
    if any(left.external_ids[key] == right.external_ids[key] for key in shared_namespaces):
        return True
    if any(left.external_ids[key] != right.external_ids[key] for key in shared_namespaces):
        return False
    right_titles = {normalize_name(right.canonical_title), *(normalize_name(value) for value in right.localized_titles.values())}
    return bool(left.normalized_titles & right_titles)


def _merge_candidates(candidates: list[ProviderCandidate]) -> list[_MergedCandidate]:
    merged: list[_MergedCandidate] = []
    for candidate in candidates:
        target = next((item for item in merged if _overlaps(item, candidate)), None)
        if target:
            target.values.append(candidate)
        else:
            merged.append(_MergedCandidate([candidate]))
    return merged


def _contains_normalized(values: list[str], expected: str | None) -> bool:
    return bool(expected) and normalize_name(expected) in {normalize_name(value) for value in values}


def _assess(
    merged: _MergedCandidate,
    query: str,
    locale: str,
    context: ResolutionContext,
) -> CandidateAssessment:
    titles = [value.canonical_title for value in merged.values]
    titles.extend(title for value in merged.values for title in value.localized_titles.values())
    normalized_query = normalize_name(query)
    exact = normalized_query in {normalize_name(title) for title in titles}
    similarity = max((SequenceMatcher(None, normalized_query, normalize_name(title)).ratio() for title in titles), default=0)
    reasons: list[str] = []
    score = 0.0
    if exact:
        score += 0.5
        reasons.append("exact official/localized title match")
    else:
        score += 0.25 * similarity
        reasons.append(f"title similarity {similarity:.2f}")

    locale_prefix = locale.casefold().split("-")[0]
    if any(key.casefold().split("-")[0] == locale_prefix for key in merged.titles):
        score += 0.06
        reasons.append(f"localized title available for {locale}")

    providers = sorted({value.provider for value in merged.values})
    provider_weight = min(0.12, 0.06 * len(providers))
    score += provider_weight
    reasons.append(f"supported by {', '.join(providers)}")

    external_ids = merged.external_ids
    if external_ids:
        score += 0.06
        reasons.append("stable external identifier present")
    if context.external_ids and any(external_ids.get(key) == value for key, value in context.external_ids.items()):
        score += 0.14
        reasons.append("requested external identifier matched")

    developers = sorted({name for value in merged.values for name in value.developers})
    publishers = sorted({name for value in merged.values for name in value.publishers})
    platforms = sorted({name for value in merged.values for name in value.platforms})
    if _contains_normalized(developers, context.developer):
        score += 0.08
        reasons.append("developer context matched")
    if _contains_normalized(publishers, context.publisher):
        score += 0.06
        reasons.append("publisher context matched")
    if _contains_normalized(platforms, context.platform):
        score += 0.04
        reasons.append("platform context matched")
    elif platforms:
        score += 0.02
        reasons.append("platform listing present")

    score = min(score, 1.0)
    localized_titles = merged.titles
    canonical = (
        localized_titles.get(locale)
        or localized_titles.get(locale_prefix)
        or localized_titles.get("en")
        or merged.values[0].canonical_title
    )
    evidence = [value.evidence for value in merged.values]
    entity = GameEntity(
        game_id=_stable_game_id(external_ids, canonical),
        canonical_title=canonical,
        original_title=next((value.original_title for value in merged.values if value.original_title), None),
        localized_titles=localized_titles,
        external_ids=external_ids,
        developers=developers,
        publishers=publishers,
        resolution_status="unresolved",
        resolution_confidence=round(score, 4),
        resolution_evidence_ids=[item.evidence_id for item in evidence],
        resolved_at=datetime.now(timezone.utc),
        release_dates={key: date for value in merged.values for key, date in value.release_dates.items()},
        genres=sorted({genre for value in merged.values for genre in value.genres}),
        franchise=next((value.franchise for value in merged.values if value.franchise), None),
        official_urls=sorted({url for value in merged.values for url in value.official_urls}),
        platforms=platforms,
    )
    return CandidateAssessment(
        entity=entity,
        score=round(score, 4),
        reasons=reasons,
        evidence=evidence,
        providers=providers,
    )


def resolve_game(
    name: str,
    *,
    locale: str | None = None,
    context: ResolutionContext | None = None,
    providers: list[ResolverProvider] | None = None,
    cache: ResolverCache | None = None,
) -> ResolutionResult:
    """Resolve a free-text name while surfacing ambiguity and provider failures."""

    name = name.strip()
    locale = locale or infer_locale(name)
    context = context or ResolutionContext()
    providers = providers or [WikidataResolverProvider(), SteamResolverProvider()]
    cache = cache or ResolverCache(Path(".cache/resolver"))
    failures: list[ProviderFailure] = []
    raw_candidates: list[ProviderCandidate] = []
    for provider in providers:
        try:
            candidates = cache.get(provider.name, name, locale)
            if candidates is None:
                candidates = provider.search(name, locale)
                cache.set(provider.name, name, locale, candidates)
            raw_candidates.extend(candidates)
        except (CollectionError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            failures.append(
                ProviderFailure(provider=provider.name, error_type=type(exc).__name__, reason=str(exc))
            )

    assessments = sorted(
        (_assess(candidate, name, locale, context) for candidate in _merge_candidates(raw_candidates)),
        key=lambda item: (-item.score, item.entity.canonical_title.casefold(), item.entity.game_id),
    )
    partial = bool(failures) and bool(assessments)
    if not assessments:
        reason = "no provider returned a plausible game candidate"
        if failures:
            reason = "all available provider paths failed or returned no candidates"
        return ResolutionResult(
            input_name=name, locale=locale, status="unresolved", game=None, candidates=[], reasons=[reason],
            provider_failures=failures, partial=False,
        )

    top = assessments[0]
    runner_up = assessments[1] if len(assessments) > 1 else None
    close_competition = runner_up is not None and top.score - runner_up.score < 0.12
    if top.score >= 0.7 and not close_competition:
        top.entity.resolution_status = ResolutionStatus.RESOLVED
        top.entity.resolution_confidence = top.score
        reasons = ["one candidate passed the resolution threshold with a safe margin"]
        if partial:
            reasons.append("resolution is partial because at least one provider failed")
        return ResolutionResult(
            input_name=name, locale=locale, status="resolved", game=top.entity, candidates=assessments,
            reasons=reasons, provider_failures=failures, partial=partial,
        )

    if runner_up is not None and top.score >= 0.45 and close_competition:
        for assessment in assessments:
            assessment.entity.resolution_status = ResolutionStatus.NEEDS_CHOICE
        return ResolutionResult(
            input_name=name, locale=locale, status="needs_choice", game=None, candidates=assessments,
            reasons=["multiple candidates are too close to choose safely"], provider_failures=failures, partial=partial,
        )

    return ResolutionResult(
        input_name=name, locale=locale, status="unresolved", game=None, candidates=assessments,
        reasons=["candidate evidence did not meet the automatic resolution threshold"],
        provider_failures=failures, partial=partial,
    )
