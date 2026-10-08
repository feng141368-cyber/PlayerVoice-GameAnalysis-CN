"""Creator Mode research brief over the shared Intelligence Core."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import Field, model_validator

from ..models import ContractModel, Insight
from .contracts import ModeClaim
from .core import IntelligenceCoreSnapshot


class PositionEvidence(ContractModel):
    evidence_id: str
    statement: str


class ControversyPosition(ContractModel):
    label: str
    summary: str
    evidence_ids: list[str] = Field(min_length=2)
    representative_statements: list[PositionEvidence] = Field(min_length=1)


class CreatorControversy(ContractModel):
    topic: str
    question: str
    side_a: ControversyPosition
    side_b: ControversyPosition
    insight_ids: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    evidence_coverage: dict
    research_gap: str

    @model_validator(mode="after")
    def require_distinguishable_positions(self) -> "CreatorControversy":
        if set(self.side_a.evidence_ids).intersection(self.side_b.evidence_ids):
            raise ValueError("controversy positions must use distinguishable evidence")
        return self


class ResearchQuestion(ContractModel):
    question: str
    classification: Literal["research_question"] = "research_question"
    rationale: str
    insight_ids: list[str]
    evidence_ids: list[str]
    not_an_established_finding: bool = True


class CreatorBrief(ContractModel):
    game_id: str
    game_title: str
    game_current_context: list[ModeClaim]
    praise: list[ModeClaim]
    complaints: list[ModeClaim]
    controversy_status: str
    controversies: list[CreatorControversy]
    questions_worth_investigating: list[ResearchQuestion]
    research_gaps: list[ModeClaim]
    platform_language_differences: list[ModeClaim]
    representative_evidence_ids: list[str]


def _claim_id(label: str, values: list[str]) -> str:
    raw = json.dumps([label, sorted(values)], ensure_ascii=False, separators=(",", ":"))
    return f"claim_{hashlib.sha256(raw.encode()).hexdigest()[:20]}"


def _insight_claim(insight: Insight) -> ModeClaim:
    evidence_ids = list(
        dict.fromkeys([*insight.supporting_evidence_ids, *insight.challenging_evidence_ids])
    )
    return ModeClaim(
        claim_id=_claim_id(insight.insight_type.value, [insight.insight_id]),
        label=insight.insight_type.value,
        statement=insight.statement,
        layer="player_evidence",
        taxonomy_node=insight.taxonomy_nodes[0] if insight.taxonomy_nodes else None,
        insight_ids=[insight.insight_id],
        evidence_ids=evidence_ids,
        confidence=insight.confidence,
        uncertainty=insight.uncertainty,
    )


def _insufficient(label: str, statement: str) -> ModeClaim:
    return ModeClaim(
        claim_id=_claim_id(label, [statement]),
        label=label,
        statement=statement,
        layer="insufficient",
        uncertainty=["The current sample does not support an affirmative claim."],
    )


def _fact_context(snapshot: IntelligenceCoreSnapshot) -> list[ModeClaim]:
    allowed = {"title", "developer", "publisher", "release_date"}
    claims = []
    for fact in snapshot.facts:
        if fact.fact_type not in allowed:
            continue
        value = json.dumps(fact.value, ensure_ascii=False) if not isinstance(fact.value, str) else fact.value
        claims.append(
            ModeClaim(
                claim_id=_claim_id(fact.fact_type, [fact.fact_id]),
                label=fact.fact_type,
                statement=f"{fact.fact_type}: {value}",
                layer="fact",
                fact_ids=[fact.fact_id],
                evidence_ids=[fact.source_evidence_id],
                confidence=fact.confidence,
            )
        )
    return claims


def _position_statements(
    snapshot: IntelligenceCoreSnapshot,
    evidence_ids: list[str],
) -> list[PositionEvidence]:
    return [
        PositionEvidence(
            evidence_id=evidence_id,
            statement=" ".join(snapshot.evidence_by_id[evidence_id].original_text.split())[:240],
        )
        for evidence_id in evidence_ids[:3]
        if evidence_id in snapshot.evidence_by_id
    ]


def _controversies(snapshot: IntelligenceCoreSnapshot) -> list[CreatorControversy]:
    results = []
    for insight in snapshot.insight_bundle.player_insights:
        if insight.insight_type.value != "controversy":
            continue
        side_a = list(dict.fromkeys(insight.supporting_evidence_ids))
        side_b = list(dict.fromkeys(insight.challenging_evidence_ids))
        # Creator Mode requires more than opposing sentiment flags: each side
        # needs at least two independently traceable statements on one topic.
        if len(side_a) < 2 or len(side_b) < 2:
            continue
        topic = insight.taxonomy_nodes[0] if insight.taxonomy_nodes else "the topic"
        results.append(
            CreatorControversy(
                topic=topic,
                question=f"Why do players in this sample hold different views about {topic}?",
                side_a=ControversyPosition(
                    label="Positive position",
                    summary=f"Some collected players express positive views about {topic}.",
                    evidence_ids=side_a,
                    representative_statements=_position_statements(snapshot, side_a),
                ),
                side_b=ControversyPosition(
                    label="Critical position",
                    summary=f"Other collected players express negative views about {topic}.",
                    evidence_ids=side_b,
                    representative_statements=_position_statements(snapshot, side_b),
                ),
                insight_ids=[insight.insight_id],
                confidence=insight.confidence,
                evidence_coverage=insight.sample_scope,
                research_gap=(
                    "The sample establishes disagreement, but not which player segments, play stages, "
                    "or design elements explain the difference."
                ),
            )
        )
    return results


def _research_questions(
    complaints: list[Insight],
    controversies: list[CreatorControversy],
) -> list[ResearchQuestion]:
    questions = [
        ResearchQuestion(
            question=value.question,
            rationale=value.research_gap,
            insight_ids=value.insight_ids,
            evidence_ids=list(dict.fromkeys([*value.side_a.evidence_ids, *value.side_b.evidence_ids])),
        )
        for value in controversies
    ]
    for insight in complaints:
        topic = insight.taxonomy_nodes[0] if insight.taxonomy_nodes else "this issue"
        questions.append(
            ResearchQuestion(
                question=f"Which player contexts and play stages are associated with complaints about {topic}?",
                rationale=(
                    "The evidence establishes complaints in the collected sample, but does not establish "
                    "their prevalence or affected player segments."
                ),
                insight_ids=[insight.insight_id],
                evidence_ids=insight.supporting_evidence_ids,
            )
        )
    unique = {}
    for question in questions:
        unique.setdefault(question.question, question)
    return list(unique.values())[:8]


def build_creator_brief(snapshot: IntelligenceCoreSnapshot) -> CreatorBrief:
    insights = snapshot.insight_bundle.player_insights
    praise_insights = [item for item in insights if item.insight_type.value == "praise"]
    complaint_insights = [item for item in insights if item.insight_type.value == "complaint"]
    gap_insights = [item for item in insights if item.insight_type.value == "research_gap"]
    difference_insights = [
        item
        for item in insights
        if item.insight_type.value == "difference"
        and len(item.sample_scope.get("sources", {})) >= 2
        and all(count >= 2 for count in item.sample_scope.get("sources", {}).values())
    ]
    controversies = _controversies(snapshot)
    praise = [_insight_claim(item) for item in praise_insights] or [
        _insufficient("praise", "No evidence-bounded praise was detected.")
    ]
    complaints = [_insight_claim(item) for item in complaint_insights] or [
        _insufficient("complaints", "No evidence-bounded complaint was detected.")
    ]
    gaps = [_insight_claim(item) for item in gap_insights] or [
        _insufficient("research_gap", "No explicit research-gap Insight was generated.")
    ]
    differences = [_insight_claim(item) for item in difference_insights] or [
        _insufficient(
            "platform_language_difference",
            "Insufficient comparable multi-source evidence for a platform or language difference claim.",
        )
    ]
    representative = list(
        dict.fromkeys(
            evidence_id
            for claim in [*praise, *complaints, *gaps, *differences]
            for evidence_id in claim.evidence_ids
        )
    )[:20]
    return CreatorBrief(
        game_id=snapshot.game.game_id,
        game_title=snapshot.game.canonical_title,
        game_current_context=_fact_context(snapshot),
        praise=praise,
        complaints=complaints,
        controversy_status=(
            f"{len(controversies)} well-supported controversy topic(s) detected."
            if controversies
            else "No well-supported controversy detected."
        ),
        controversies=controversies,
        questions_worth_investigating=_research_questions(complaint_insights, controversies),
        research_gaps=gaps,
        platform_language_differences=differences,
        representative_evidence_ids=representative,
    )


def render_creator_markdown(brief: CreatorBrief) -> str:
    lines = [f"# Creator Research Brief — {brief.game_title}", ""]
    sections = [
        ("Game / current context", brief.game_current_context),
        ("What players praise", brief.praise),
        ("What players complain about", brief.complaints),
    ]
    for title, claims in sections:
        lines.extend([f"## {title}", ""])
        for claim in claims:
            layer = "Fact Layer" if claim.layer == "fact" else "Player Evidence" if claim.layer == "player_evidence" else "Insufficient Evidence"
            lines.append(f"- **[{layer}] {claim.label}:** {claim.statement}")
            if claim.insight_ids:
                lines.append(f"  - Insight: {', '.join(f'`{value}`' for value in claim.insight_ids)}")
            if claim.evidence_ids:
                lines.append(f"  - Evidence: {', '.join(f'`{value}`' for value in claim.evidence_ids)}")
        lines.append("")
    lines.extend(["## Controversies", "", brief.controversy_status, ""])
    for value in brief.controversies:
        lines.extend([f"### {value.question}", "", f"- Side A: {value.side_a.summary}", f"  - Evidence: {', '.join(f'`{item}`' for item in value.side_a.evidence_ids)}", f"- Side B: {value.side_b.summary}", f"  - Evidence: {', '.join(f'`{item}`' for item in value.side_b.evidence_ids)}", f"- Evidence coverage: `{json.dumps(value.evidence_coverage, ensure_ascii=False, sort_keys=True)}`", f"- Research gap: {value.research_gap}", ""])
    lines.extend(["## Questions worth investigating", ""])
    for value in brief.questions_worth_investigating:
        lines.append(f"- **[Research question, not established finding]** {value.question}")
        lines.append(f"  - Basis: {value.rationale}")
        lines.append(f"  - Evidence: {', '.join(f'`{item}`' for item in value.evidence_ids)}")
    lines.extend(["", "## Research gaps", ""])
    for claim in brief.research_gaps:
        lines.append(f"- {claim.statement}")
        if claim.evidence_ids:
            lines.append(f"  - Evidence: {', '.join(f'`{value}`' for value in claim.evidence_ids)}")
    lines.extend(["", "## Platform / language differences", ""])
    for claim in brief.platform_language_differences:
        lines.append(f"- **[{claim.layer.replace('_', ' ').title()}]** {claim.statement}")
    lines.extend(["", "> This is a research brief, not a finished review script or population-level claim.", ""])
    return "\n".join(lines)
