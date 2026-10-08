"""Player Mode preference parsing and evidence-backed fit rendering."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from typing import Any, Iterable, Literal

from pydantic import Field

from ..models import ContractModel, FactRecord, Insight
from .contracts import ModeClaim
from .core import IntelligenceCoreSnapshot


PREFERENCE_PARSER_VERSION = "preference-rules-v1"

PREFERENCE_TERMS: dict[str, list[str]] = {
    "exploration": ["exploration", "explore", "open world", "探索", "开放世界"],
    "story": ["story", "plot", "narrative", "剧情", "叙事"],
    "characters": ["character", "characters", "角色", "人物塑造", "角色塑造"],
    "graphics": ["graphics", "visuals", "画面", "画质"],
    "audio": ["audio", "music", "soundtrack", "音乐", "音效", "声音"],
    "combat": ["combat", "gunplay", "战斗", "打击感"],
    "pvp": ["pvp", "competitive", "竞技", "排位"],
    "daily_commitment": [
        "daily commitment",
        "daily chores",
        "daily tasks",
        "每天必须上线",
        "每天上线",
        "日常任务",
        "日常负担",
    ],
    "grind": ["grind", "grindy", "重复刷", "肝"],
    "monetisation": ["monetisation", "monetization", "spending", "氪金", "商业化"],
    "controls": ["controls", "controller", "keyboard", "操作", "手柄", "键鼠"],
    "performance": ["performance", "fps", "性能", "帧率", "优化"],
}

NEGATION_CUES = ["不喜欢", "不想", "不接受", "讨厌", "避免", "不要", "dislike", "don't like", "do not like", "avoid", "hate"]


class PreferenceProfile(ContractModel):
    important: list[str]
    avoid: list[str]
    constraints: dict[str, Any]
    raw_text: str | None = None
    parser_version: str = PREFERENCE_PARSER_VERSION


class FitDimension(ContractModel):
    dimension: str
    assessment: Literal["likely_match", "possible_friction", "uncertain"]
    rationale: str
    insight_ids: list[str]
    evidence_ids: list[str]
    evidence_count: int = Field(ge=0)
    source_count: int = Field(ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    uncertainty: list[str] = Field(default_factory=list)


class PlayerReport(ContractModel):
    game_id: str
    game_title: str
    preference_profile: PreferenceProfile
    what_is_this_game: list[ModeClaim]
    where_can_i_play_it: list[ModeClaim]
    can_i_run_it: list[ModeClaim]
    controls: list[ModeClaim]
    what_players_praise: list[ModeClaim]
    what_players_complain_about: list[ModeClaim]
    what_to_pay_attention_to: list[ModeClaim]
    preference_fit: list[FitDimension]


def _dedupe(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _minutes_per_day(text: str) -> int | None:
    normalised = text.casefold()
    chinese_hours = {"半": 0.5, "一": 1, "一个": 1, "两": 2, "二": 2, "三": 3, "四": 4}
    match = re.search(r"(\d+(?:\.\d+)?|半|一个|一|两|二|三|四)\s*(?:个)?小时", normalised)
    if match:
        raw = match.group(1)
        hours = chinese_hours.get(raw, float(raw) if raw.replace(".", "", 1).isdigit() else 0)
        return int(hours * 60)
    match = re.search(r"(\d+)\s*(?:分钟|minutes?|mins?)", normalised)
    if match:
        return int(match.group(1))
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)", normalised)
    if match:
        return int(float(match.group(1)) * 60)
    return None


def parse_preference_profile(value: str | dict[str, Any] | PreferenceProfile | None) -> PreferenceProfile:
    if isinstance(value, PreferenceProfile):
        return value
    if isinstance(value, dict):
        return PreferenceProfile.model_validate(value)
    text = value or ""
    normalised = text.casefold()
    important: list[str] = []
    avoid: list[str] = []
    for topic, terms in PREFERENCE_TERMS.items():
        positions = [normalised.find(term.casefold()) for term in terms if normalised.find(term.casefold()) >= 0]
        if not positions:
            continue
        position = min(positions)
        clause_start = max(
            normalised.rfind(mark, 0, position)
            for mark in ["。", ".", "！", "!", "？", "?", "；", ";", "，", ","]
        )
        prefix = normalised[max(clause_start + 1, position - 24):position]
        if any(cue in prefix for cue in NEGATION_CUES):
            avoid.append(topic)
        else:
            important.append(topic)
    important = [topic for topic in _dedupe(important) if topic not in avoid]
    constraints: dict[str, Any] = {}
    minutes = _minutes_per_day(text)
    if minutes is not None:
        constraints["available_time_minutes_per_day"] = minutes
    return PreferenceProfile(
        important=important,
        avoid=_dedupe(avoid),
        constraints=constraints,
        raw_text=value,
    )


def _claim_id(label: str, ids: Iterable[str]) -> str:
    payload = json.dumps([label, sorted(ids)], ensure_ascii=False, separators=(",", ":"))
    return f"claim_{hashlib.sha256(payload.encode()).hexdigest()[:20]}"


def _fact_claim(fact: FactRecord, label: str, statement: str) -> ModeClaim:
    return ModeClaim(
        claim_id=_claim_id(label, [fact.fact_id]),
        label=label,
        statement=statement,
        layer="fact",
        fact_ids=[fact.fact_id],
        evidence_ids=[fact.source_evidence_id],
        confidence=fact.confidence,
        uncertainty=[] if fact.verification_status.value == "verified" else ["Fact is not fully verified."],
    )


def _insight_claim(insight: Insight, label: str | None = None) -> ModeClaim:
    evidence_ids = _dedupe([*insight.supporting_evidence_ids, *insight.challenging_evidence_ids])
    return ModeClaim(
        claim_id=_claim_id(label or insight.insight_type.value, [insight.insight_id]),
        label=label or insight.insight_type.value,
        statement=insight.statement,
        layer="player_evidence",
        taxonomy_node=insight.taxonomy_nodes[0] if insight.taxonomy_nodes else None,
        insight_ids=[insight.insight_id],
        evidence_ids=evidence_ids,
        confidence=insight.confidence,
        uncertainty=insight.uncertainty,
    )


def _insufficient(label: str, statement: str, topic: str | None = None) -> ModeClaim:
    return ModeClaim(
        claim_id=_claim_id(label, [topic or statement]),
        label=label,
        statement=statement,
        layer="insufficient",
        taxonomy_node=topic,
        uncertainty=["Insufficient collected evidence; absence is not a neutral or positive finding."],
    )


def _fact_value(fact: FactRecord) -> str:
    if isinstance(fact.value, dict):
        return ", ".join(f"{key}={value}" for key, value in fact.value.items())
    if isinstance(fact.value, list):
        return ", ".join(str(value) for value in fact.value)
    return str(fact.value)


def _facts(snapshot: IntelligenceCoreSnapshot, *types: str) -> list[FactRecord]:
    return [fact for fact in snapshot.facts if fact.fact_type in types]


def _topic_insights(snapshot: IntelligenceCoreSnapshot, topic: str) -> list[Insight]:
    aliases = {
        "audio": {"audio", "audio_music", "audio_sound_design", "audio_voice_acting"},
    }
    accepted = aliases.get(topic, {topic})
    return [
        insight
        for insight in snapshot.insight_bundle.player_insights
        if accepted.intersection(insight.taxonomy_nodes)
    ]


def _fit(snapshot: IntelligenceCoreSnapshot, profile: PreferenceProfile) -> list[FitDimension]:
    dimensions: list[FitDimension] = []
    desired = [(topic, False) for topic in profile.important] + [(topic, True) for topic in profile.avoid]
    for topic, avoided in desired:
        insights = _topic_insights(snapshot, topic)
        praise = [item for item in insights if item.insight_type.value == "praise"]
        complaints = [item for item in insights if item.insight_type.value == "complaint"]
        if avoided and (praise or complaints):
            supporting = complaints or praise
            assessment = "possible_friction"
            rationale = (
                f"Collected evidence discusses {topic}, which the player wants to avoid; "
                "review the linked sample before deciding whether the exposure is material."
            )
        elif not avoided and praise:
            supporting = praise
            assessment = "likely_match"
            rationale = f"The collected sample contains player praise linked to {topic}."
        elif not avoided and complaints:
            supporting = complaints
            assessment = "possible_friction"
            rationale = f"The desired dimension {topic} appears mainly in complaint evidence."
        else:
            supporting = []
            assessment = "uncertain"
            rationale = f"No evidence-bounded Insight supports a reliable fit judgment for {topic}."
        evidence_ids = _dedupe(
            value
            for insight in supporting
            for value in [*insight.supporting_evidence_ids, *insight.challenging_evidence_ids]
        )
        sources = {
            snapshot.evidence_by_id[value].source
            for value in evidence_ids
            if value in snapshot.evidence_by_id
        }
        dimensions.append(
            FitDimension(
                dimension=topic,
                assessment=assessment,
                rationale=rationale,
                insight_ids=[item.insight_id for item in supporting],
                evidence_ids=evidence_ids,
                evidence_count=len(evidence_ids),
                source_count=len(sources),
                confidence=max((item.confidence for item in supporting), default=None),
                uncertainty=(
                    ["Public player evidence is self-selected and not a population estimate."]
                    if supporting
                    else ["Insufficient evidence; no fit score is inferred."]
                ),
            )
        )
    minutes = profile.constraints.get("available_time_minutes_per_day")
    if minutes is not None:
        daily = _topic_insights(snapshot, "daily_commitment")
        evidence_ids = _dedupe(
            value for insight in daily for value in insight.supporting_evidence_ids
        )
        dimensions.append(
            FitDimension(
                dimension="available_time",
                assessment="possible_friction" if daily else "uncertain",
                rationale=(
                    f"The player reports about {minutes} minutes/day; daily-commitment evidence should be reviewed."
                    if daily
                    else f"The player reports about {minutes} minutes/day, but collected evidence cannot establish required daily commitment."
                ),
                insight_ids=[item.insight_id for item in daily],
                evidence_ids=evidence_ids,
                evidence_count=len(evidence_ids),
                source_count=len({snapshot.evidence_by_id[value].source for value in evidence_ids}),
                confidence=max((item.confidence for item in daily), default=None),
                uncertainty=["Available-time fit is not inferred from missing commitment evidence."] if not daily else [],
            )
        )
    return dimensions


def build_player_report(
    snapshot: IntelligenceCoreSnapshot,
    preferences: str | dict[str, Any] | PreferenceProfile | None,
) -> PlayerReport:
    profile = parse_preference_profile(preferences)
    title_facts = _facts(snapshot, "title")
    developer_facts = _facts(snapshot, "developer", "publisher")
    release_facts = _facts(snapshot, "release_date")
    identity = [
        _fact_claim(fact, fact.fact_type, f"{fact.fact_type}: {_fact_value(fact)}")
        for fact in [*title_facts, *developer_facts, *release_facts]
    ]
    availability = [
        _fact_claim(
            fact,
            fact.fact_type,
            f"{fact.platform or fact.territory or 'global'} {fact.fact_type}: {_fact_value(fact)}",
        )
        for fact in _facts(snapshot, "platform_support", "cross_play", "cross_save")
    ]
    requirements = [
        _fact_claim(
            fact,
            fact.fact_type,
            f"{fact.platform or 'platform'} {fact.fact_type}: {_fact_value(fact)}",
        )
        for fact in _facts(
            snapshot,
            "minimum_requirements",
            "recommended_requirements",
            "storage_requirement",
        )
    ]
    performance = _topic_insights(snapshot, "performance")
    requirements.extend(_insight_claim(item, "player-reported performance") for item in performance)
    if not requirements:
        requirements = [_insufficient("can_i_run_it", "No verified requirements or player performance evidence were collected.")]

    control_facts = _facts(snapshot, "input_support", "keyboard_mouse", "controller", "touch", "remapping")
    control_insights = _topic_insights(snapshot, "controls")
    controls = [
        *[_fact_claim(fact, "control support", _fact_value(fact)) for fact in control_facts],
        *[_insight_claim(item, "player-reported controls") for item in control_insights],
    ] or [_insufficient("controls", "Controller, keyboard/mouse, touch, and remapping support are not established by the collected evidence.", "controls")]

    insights = snapshot.insight_bundle.player_insights
    praises = [_insight_claim(item) for item in insights if item.insight_type.value == "praise"]
    complaints = [_insight_claim(item) for item in insights if item.insight_type.value == "complaint"]
    attention = complaints[:]
    if not attention:
        attention.append(_insufficient("attention", "No bounded complaint Insight was available; this is not evidence that the game has no issues."))
    return PlayerReport(
        game_id=snapshot.game.game_id,
        game_title=snapshot.game.canonical_title,
        preference_profile=profile,
        what_is_this_game=identity,
        where_can_i_play_it=availability or [_insufficient("availability", "No verified platform availability facts were collected.")],
        can_i_run_it=requirements,
        controls=controls,
        what_players_praise=praises or [_insufficient("praise", "No evidence-bounded praise was detected in this sample.")],
        what_players_complain_about=complaints or [_insufficient("complaints", "No evidence-bounded complaint was detected in this sample.")],
        what_to_pay_attention_to=attention,
        preference_fit=_fit(snapshot, profile),
    )


def render_player_markdown(report: PlayerReport) -> str:
    lines = [f"# Player Research Summary — {report.game_title}", ""]
    lines.extend(["## Preference profile", "", f"- Important: {', '.join(report.preference_profile.important) or 'none supplied'}", f"- Avoid: {', '.join(report.preference_profile.avoid) or 'none supplied'}", f"- Constraints: `{json.dumps(report.preference_profile.constraints, ensure_ascii=False)}`", ""])
    sections = [
        ("What is this game?", report.what_is_this_game),
        ("Where can I play it?", report.where_can_i_play_it),
        ("Can I run it?", report.can_i_run_it),
        ("Controls", report.controls),
        ("What players praise", report.what_players_praise),
        ("What players complain about", report.what_players_complain_about),
        ("What should I pay attention to?", report.what_to_pay_attention_to),
    ]
    layer_labels = {"fact": "Fact Layer", "player_evidence": "Player Evidence", "insufficient": "Insufficient Evidence", "inference": "Inference", "hypothesis": "Hypothesis"}
    for title, claims in sections:
        lines.extend([f"## {title}", ""])
        for claim in claims:
            lines.append(f"- **[{layer_labels[claim.layer]}] {claim.label}:** {claim.statement}")
            if claim.insight_ids:
                lines.append(f"  - Insight: {', '.join(f'`{value}`' for value in claim.insight_ids)}")
            if claim.evidence_ids:
                lines.append(f"  - Evidence: {', '.join(f'`{value}`' for value in claim.evidence_ids)}")
        lines.append("")
    lines.extend(["## Preference fit", ""])
    labels = {"likely_match": "Likely Match", "possible_friction": "Possible Friction", "uncertain": "Uncertain / Insufficient Evidence"}
    for assessment in ("likely_match", "possible_friction", "uncertain"):
        lines.extend([f"### {labels[assessment]}", ""])
        values = [item for item in report.preference_fit if item.assessment == assessment]
        if not values:
            lines.append("- None supported by the current sample.")
        for item in values:
            lines.append(f"- **{item.dimension}:** {item.rationale}")
            if item.evidence_ids:
                lines.append(f"  - Evidence ({item.evidence_count}, {item.source_count} source(s)): {', '.join(f'`{value}`' for value in item.evidence_ids)}")
        lines.append("")
    lines.append("> This report provides evidence-backed dimensions, not a universal score or purchase instruction.")
    return "\n".join(lines) + "\n"
