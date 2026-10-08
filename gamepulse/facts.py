"""Official Fact Layer adapters, reconciliation, storage, and fact-only bundles."""

from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Protocol

from pydantic import Field

from .http import request_json
from .models import (
    ContractModel,
    EvidenceItem,
    FactRecord,
    GameEntity,
    Provenance,
    QueryPlan,
    SourceAuthority,
)


def _stable_id(prefix: str, *parts: Any) -> str:
    serialized = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return f"{prefix}_{hashlib.sha256(serialized.encode('utf-8')).hexdigest()[:20]}"


def _clean_html(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value)
    lines = [re.sub(r"\s+", " ", line).strip() for line in value.splitlines()]
    return "\n".join(line for line in lines if line)


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


class FactBundle(ContractModel):
    game_id: str
    facts: list[FactRecord]
    evidence: list[EvidenceItem]
    warnings: list[str] = Field(default_factory=list)

    def facts_by_type(self, fact_type: str) -> list[FactRecord]:
        return [fact for fact in self.facts if fact.fact_type == fact_type]


class CanIRunItBundle(ContractModel):
    game_id: str
    platform: str | None
    layer: str = "official_fact"
    minimum_requirements: list[FactRecord]
    recommended_requirements: list[FactRecord]
    storage_requirements: list[FactRecord]
    input_support: list[FactRecord]
    supported_languages: list[FactRecord]
    evidence_ids: list[str]
    missing_fact_types: list[str]


class FactAdapter(Protocol):
    name: str

    def collect(
        self,
        game: GameEntity,
        *,
        run_id: str,
        query_plan: QueryPlan | None = None,
    ) -> FactBundle: ...


class _FactEmitter:
    def __init__(
        self,
        *,
        game: GameEntity,
        evidence: EvidenceItem,
        authority: SourceAuthority,
        retrieved_at: datetime,
    ):
        self.game = game
        self.evidence = evidence
        self.authority = authority
        self.retrieved_at = retrieved_at
        self.facts: list[FactRecord] = []

    def add(
        self,
        fact_type: str,
        value: Any,
        *,
        unit: str | None = None,
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
        territory: str | None = None,
        platform: str | None = None,
        confidence: float | None = None,
    ) -> None:
        if value is None or value == "" or value == [] or value == {}:
            return
        fact_id = _stable_id(
            "fact", self.game.game_id, fact_type, value, unit, territory, platform, self.evidence.evidence_id,
        )
        self.facts.append(
            FactRecord(
                fact_id=fact_id,
                game_id=self.game.game_id,
                fact_type=fact_type,
                value=value,
                unit=unit,
                valid_from=valid_from,
                valid_to=valid_to,
                territory=territory,
                platform=platform,
                source_evidence_id=self.evidence.evidence_id,
                source_authority=self.authority,
                verification_status="verified",
                confidence=confidence if confidence is not None else (1.0 if self.authority == SourceAuthority.OFFICIAL else 0.95),
                retrieved_at=self.retrieved_at,
            )
        )


def _source_evidence(
    *,
    game: GameEntity,
    run_id: str,
    source: str,
    source_content_id: str,
    source_url: str | None,
    original_text: str,
    retrieved_at: datetime,
    authority: SourceAuthority,
    query_plan: QueryPlan | None = None,
    evidence_kind: str = "fact_source",
) -> EvidenceItem:
    checksum = hashlib.sha256(original_text.encode("utf-8")).hexdigest()
    source_class = "official" if authority == SourceAuthority.OFFICIAL else "platform_store"
    return EvidenceItem(
        evidence_id=_stable_id("ev", source, source_content_id, checksum),
        game_id=game.game_id,
        evidence_kind=evidence_kind,
        access_scope="public",
        dataset_id=None,
        source=source,
        source_content_id=source_content_id,
        source_url=source_url,
        source_reference=None if source_url else f"{source}:{source_content_id}",
        title=None,
        original_text=original_text,
        normalized_text=None,
        language=None,
        published_at=None,
        retrieved_at=retrieved_at,
        run_id=run_id,
        query_id=query_plan.query_id if query_plan else None,
        matched_alias_ids=query_plan.alias_ids if query_plan else [],
        retrieval_method="api" if source == "steam" else "official_feed",
        relevance_label="relevant",
        relevance_score=1,
        relevance_reasons=["official or platform-store fact source"],
        relevance_method_version="fact-layer-v1",
        platform=source,
        source_metadata={},
        provenance=Provenance(
            source_class=source_class,
            collector_version="fact-layer-v1",
            terms_or_permission_reference=None,
            content_checksum=checksum,
            raw_snapshot_reference=None,
            contains_personal_data=False,
            redaction_status="not_required",
        ),
    )


def _storage_amount(requirements: str) -> tuple[float, str] | None:
    patterns = [
        r"(?:storage|hard drive|disk space)\s*:\s*([\d.]+)\s*(gb|mb|tb)",
        r"([\d.]+)\s*(gb|mb|tb)\s*(?:available space|storage)",
    ]
    for pattern in patterns:
        match = re.search(pattern, requirements, flags=re.IGNORECASE)
        if match:
            return float(match.group(1)), match.group(2).upper()
    return None


def _supported_languages(value: str) -> list[str]:
    cleaned = _clean_html(value).replace("*", "")
    return [part.strip() for part in cleaned.split(",") if part.strip()]


class SteamStoreFactAdapter:
    """Live-capable adapter for Steam's public appdetails endpoint."""

    name = "steam"

    def __init__(self, requester=request_json, *, country: str = "US", language: str = "english"):
        self.requester = requester
        self.country = country
        self.language = language

    def collect(
        self,
        game: GameEntity,
        *,
        run_id: str,
        query_plan: QueryPlan | None = None,
    ) -> FactBundle:
        app_id = game.external_ids.get("steam_app_id")
        if not app_id:
            return FactBundle(game_id=game.game_id, facts=[], evidence=[], warnings=["steam_app_id unavailable"])
        payload = self.requester(
            "https://store.steampowered.com/api/appdetails",
            params={"appids": app_id, "l": self.language, "cc": self.country},
            headers={"User-Agent": "PlayerVoice/0.3"},
            retries=2,
            timeout=20,
        )
        app_payload = payload.get(str(app_id)) or {}
        if not app_payload.get("success") or not app_payload.get("data"):
            return FactBundle(game_id=game.game_id, facts=[], evidence=[], warnings=["Steam appdetails unavailable"])
        return self.from_payload(
            game,
            app_payload["data"],
            app_id=str(app_id),
            run_id=run_id,
            query_plan=query_plan,
            territory=self.country,
        )

    @staticmethod
    def from_payload(
        game: GameEntity,
        data: dict[str, Any],
        *,
        app_id: str,
        run_id: str,
        query_plan: QueryPlan | None = None,
        territory: str = "US",
        retrieved_at: datetime | None = None,
    ) -> FactBundle:
        retrieved_at = retrieved_at or datetime.now(timezone.utc)
        source_url = f"https://store.steampowered.com/app/{app_id}/"
        evidence = _source_evidence(
            game=game,
            run_id=run_id,
            source="steam",
            source_content_id=f"steam_app:{app_id}",
            source_url=source_url,
            original_text=_json_text(data),
            retrieved_at=retrieved_at,
            authority=SourceAuthority.PLATFORM_STORE,
            query_plan=query_plan,
        )
        emitter = _FactEmitter(
            game=game,
            evidence=evidence,
            authority=SourceAuthority.PLATFORM_STORE,
            retrieved_at=retrieved_at,
        )
        emitter.add("title", {"language": "en", "title": data.get("name")}, territory=territory)
        for developer in data.get("developers") or []:
            emitter.add("developer", str(developer), territory=territory)
        for publisher in data.get("publishers") or []:
            emitter.add("publisher", str(publisher), territory=territory)

        release = data.get("release_date") or {}
        if release.get("date"):
            emitter.add(
                "release_date",
                {"date": str(release["date"]), "coming_soon": bool(release.get("coming_soon", False))},
                territory=territory,
            )

        platform_flags = data.get("platforms") or {}
        platform_names = {"windows": "Windows", "mac": "macOS", "linux": "Linux"}
        for platform_key, supported in platform_flags.items():
            if supported:
                platform = platform_names.get(platform_key, str(platform_key))
                emitter.add("platform_support", True, territory=territory, platform=platform)

        pc_requirements = data.get("pc_requirements") or {}
        if isinstance(pc_requirements, dict):
            for tier, fact_type in (("minimum", "minimum_requirements"), ("recommended", "recommended_requirements")):
                raw = pc_requirements.get(tier)
                if raw:
                    cleaned = _clean_html(str(raw))
                    emitter.add(fact_type, cleaned, territory=territory, platform="Windows")
                    storage = _storage_amount(cleaned)
                    if storage:
                        amount, unit = storage
                        emitter.add(
                            "storage_requirement",
                            {"tier": tier, "amount": amount},
                            unit=unit,
                            territory=territory,
                            platform="Windows",
                        )

        controller_support = data.get("controller_support")
        if controller_support:
            emitter.add("input_support", {"controller": str(controller_support)}, territory=territory)
        if data.get("supported_languages"):
            emitter.add(
                "supported_languages",
                _supported_languages(str(data["supported_languages"])),
                territory=territory,
            )

        categories = {str(item.get("description", "")).casefold() for item in data.get("categories") or []}
        if "cross-platform multiplayer" in categories:
            emitter.add("cross_play", True, territory=territory)
        # Steam Cloud is deliberately not treated as cross-save. Only an explicit field is accepted.
        if "cross_save" in data:
            emitter.add("cross_save", bool(data["cross_save"]), territory=territory)
        if data.get("current_version"):
            emitter.add("current_version", str(data["current_version"]), territory=territory)
        return FactBundle(game_id=game.game_id, facts=emitter.facts, evidence=[evidence])


class StructuredOfficialFactAdapter:
    """Normalize an official, already-authorised structured metadata document."""

    name = "official"

    def __init__(self, payload: dict[str, Any]):
        self.payload = payload

    def collect(
        self,
        game: GameEntity,
        *,
        run_id: str,
        query_plan: QueryPlan | None = None,
    ) -> FactBundle:
        payload = self.payload
        retrieved_at = datetime.fromisoformat(str(payload["retrieved_at"]).replace("Z", "+00:00"))
        evidence = _source_evidence(
            game=game,
            run_id=run_id,
            source=str(payload.get("source", "official")),
            source_content_id=str(payload["source_content_id"]),
            source_url=payload.get("source_url"),
            original_text=str(payload.get("original_text") or _json_text(payload.get("facts", {}))),
            retrieved_at=retrieved_at,
            authority=SourceAuthority.OFFICIAL,
            query_plan=query_plan,
        )
        emitter = _FactEmitter(
            game=game, evidence=evidence, authority=SourceAuthority.OFFICIAL, retrieved_at=retrieved_at,
        )
        territory = payload.get("territory")
        fact_data = payload.get("facts") or {}
        for language, title in (fact_data.get("titles") or {}).items():
            emitter.add("title", {"language": language, "title": title}, territory=territory)
        for value in fact_data.get("developers") or []:
            emitter.add("developer", value, territory=territory)
        for value in fact_data.get("publishers") or []:
            emitter.add("publisher", value, territory=territory)
        for scope, value in (fact_data.get("release_dates") or {}).items():
            emitter.add("release_date", value, territory=territory, platform=scope)
        for platform in fact_data.get("platforms") or []:
            emitter.add("platform_support", True, territory=territory, platform=platform)
        for platform, tiers in (fact_data.get("requirements") or {}).items():
            if tiers.get("minimum"):
                emitter.add("minimum_requirements", tiers["minimum"], territory=territory, platform=platform)
            if tiers.get("recommended"):
                emitter.add("recommended_requirements", tiers["recommended"], territory=territory, platform=platform)
        for platform, value in (fact_data.get("storage") or {}).items():
            emitter.add(
                "storage_requirement",
                {"tier": value.get("tier", "unspecified"), "amount": value["amount"]},
                unit=value.get("unit"),
                territory=territory,
                platform=platform,
            )
        for platform, value in (fact_data.get("input_support") or {}).items():
            emitter.add("input_support", value, territory=territory, platform=platform)
        if fact_data.get("supported_languages"):
            emitter.add("supported_languages", fact_data["supported_languages"], territory=territory)
        # Absence is unknown. Emit cross-play/save only when the document explicitly supplies the key.
        if "cross_play" in fact_data:
            emitter.add("cross_play", fact_data["cross_play"], territory=territory)
        if "cross_save" in fact_data:
            emitter.add("cross_save", fact_data["cross_save"], territory=territory)
        if fact_data.get("current_version"):
            emitter.add("current_version", fact_data["current_version"], territory=territory)

        evidence_items = [evidence]
        for patch in payload.get("patch_references") or []:
            patch_text = str(patch.get("title") or patch.get("version") or "Official patch")
            patch_evidence = _source_evidence(
                game=game,
                run_id=run_id,
                source=str(payload.get("source", "official")),
                source_content_id=str(patch["source_content_id"]),
                source_url=patch.get("url"),
                original_text=patch_text,
                retrieved_at=retrieved_at,
                authority=SourceAuthority.OFFICIAL,
                query_plan=query_plan,
                evidence_kind="patch_note",
            )
            evidence_items.append(patch_evidence)
            patch_emitter = _FactEmitter(
                game=game,
                evidence=patch_evidence,
                authority=SourceAuthority.OFFICIAL,
                retrieved_at=retrieved_at,
            )
            patch_emitter.add(
                "official_patch_reference",
                {key: value for key, value in patch.items() if key != "source_content_id"},
                territory=territory,
            )
            emitter.facts.extend(patch_emitter.facts)
        return FactBundle(game_id=game.game_id, facts=emitter.facts, evidence=evidence_items)


_MULTI_VALUE_FACTS = {"title", "developer", "publisher", "platform_support", "official_patch_reference"}


def _conflict_key(fact: FactRecord) -> tuple[Any, ...] | None:
    if fact.fact_type in _MULTI_VALUE_FACTS:
        return None
    qualifier = None
    if fact.fact_type == "storage_requirement" and isinstance(fact.value, dict):
        qualifier = fact.value.get("tier")
    return fact.game_id, fact.fact_type, fact.platform, fact.territory, qualifier


def reconcile_facts(bundles: Iterable[FactBundle]) -> FactBundle:
    bundles = list(bundles)
    if not bundles:
        raise ValueError("at least one fact bundle is required")
    game_ids = {bundle.game_id for bundle in bundles}
    if len(game_ids) != 1:
        raise ValueError("cannot reconcile facts for different games")
    facts = [fact.model_copy(deep=True) for bundle in bundles for fact in bundle.facts]
    groups: dict[tuple[Any, ...], list[FactRecord]] = {}
    for fact in facts:
        key = _conflict_key(fact)
        if key is not None:
            groups.setdefault(key, []).append(fact)
    for group in groups.values():
        values = {_json_text(fact.value) for fact in group}
        if len(values) > 1:
            for fact in group:
                fact.verification_status = "conflicting"
    evidence_by_id = {
        item.evidence_id: item for bundle in bundles for item in bundle.evidence
    }
    warnings = [warning for bundle in bundles for warning in bundle.warnings]
    return FactBundle(
        game_id=next(iter(game_ids)),
        facts=facts,
        evidence=list(evidence_by_id.values()),
        warnings=warnings,
    )


class JsonFactStore:
    """Dedicated fact/evidence persistence; never reads the UGC voice table."""

    def __init__(self, root: Path):
        self.root = root

    def save(self, bundle: FactBundle) -> None:
        directory = self.root / bundle.game_id
        directory.mkdir(parents=True, exist_ok=True)
        facts = sorted(bundle.facts, key=lambda item: item.fact_id)
        evidence = sorted(bundle.evidence, key=lambda item: item.evidence_id)
        (directory / "facts.jsonl").write_text(
            "".join(json.dumps(item.to_dict(), ensure_ascii=False, sort_keys=True) + "\n" for item in facts),
            encoding="utf-8",
        )
        (directory / "evidence.jsonl").write_text(
            "".join(json.dumps(item.to_dict(), ensure_ascii=False, sort_keys=True) + "\n" for item in evidence),
            encoding="utf-8",
        )

    def query(
        self,
        game_id: str,
        *,
        fact_types: set[str] | None = None,
        platform: str | None = None,
        territory: str | None = None,
    ) -> list[FactRecord]:
        path = self.root / game_id / "facts.jsonl"
        if not path.exists():
            return []
        facts = [FactRecord.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        return [
            fact for fact in facts
            if (fact_types is None or fact.fact_type in fact_types)
            and (platform is None or fact.platform is None or fact.platform.casefold() == platform.casefold())
            and (territory is None or fact.territory is None or fact.territory.casefold() == territory.casefold())
        ]

    def evidence(self, game_id: str) -> list[EvidenceItem]:
        path = self.root / game_id / "evidence.jsonl"
        if not path.exists():
            return []
        return [EvidenceItem.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def build_can_i_run_it(
    store: JsonFactStore,
    game_id: str,
    *,
    platform: str | None = None,
    territory: str | None = None,
) -> CanIRunItBundle:
    wanted = {
        "minimum_requirements", "recommended_requirements", "storage_requirement",
        "input_support", "supported_languages",
    }
    facts = store.query(game_id, fact_types=wanted, platform=platform, territory=territory)
    by_type = {fact_type: [fact for fact in facts if fact.fact_type == fact_type] for fact_type in wanted}
    return CanIRunItBundle(
        game_id=game_id,
        platform=platform,
        minimum_requirements=by_type["minimum_requirements"],
        recommended_requirements=by_type["recommended_requirements"],
        storage_requirements=by_type["storage_requirement"],
        input_support=by_type["input_support"],
        supported_languages=by_type["supported_languages"],
        evidence_ids=sorted({fact.source_evidence_id for fact in facts}),
        missing_fact_types=sorted(fact_type for fact_type, values in by_type.items() if not values),
    )


def collect_fact_layer(
    game: GameEntity,
    adapters: Iterable[FactAdapter],
    *,
    run_id: str,
    query_plans: Iterable[QueryPlan] = (),
) -> FactBundle:
    plans_by_source = {plan.source: plan for plan in query_plans}
    bundles = [
        adapter.collect(game, run_id=run_id, query_plan=plans_by_source.get(adapter.name))
        for adapter in adapters
    ]
    return reconcile_facts(bundles) if bundles else FactBundle(game_id=game.game_id, facts=[], evidence=[])
