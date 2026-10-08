"""Public-corpus Analyst Mode with explicit epistemic boundaries."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import Field

from ..insights import DECISION_SUPPORT_DISCLAIMER
from ..models import AnalysisAnnotation, ContractModel, EvidenceItem, Insight
from .core import IntelligenceCoreSnapshot


class AnalystStage(ContractModel):
    status: Literal["observed", "inferred", "expressed_intent", "hypothesis"]
    value: str
    evidence_ids: list[str] = Field(min_length=1)
    caveat: str | None = None


class AnalystFinding(ContractModel):
    finding_id: str = Field(pattern=r"^analyst_.+")
    evidence: AnalystStage
    topic: AnalystStage
    pain_points: list[AnalystStage]
    underlying_needs: list[AnalystStage]
    expressed_behaviour_signals: list[AnalystStage]
    possible_business_relevance: list[AnalystStage]
    product_opportunities: list[AnalystStage]
    explicit_feature_requests: list[AnalystStage]
    priority: dict | None = None


class AnalystReport(ContractModel):
    game_id: str
    game_title: str
    data_scope: Literal["public_corpus_only"] = "public_corpus_only"
    observed_behaviour_data_available: bool = False
    findings: list[AnalystFinding]
    priority_disclaimer: str = DECISION_SUPPORT_DISCLAIMER
    research_gaps: list[str]
    limitations: list[str]


BEHAVIOUR_LABELS = {
    "churn_risk": "expressed_churn_intent",
    "return_intent": "expressed_return_intent",
    "recommendation_intent": "expressed_recommendation_intent",
    "payment_intent": "expressed_payment_intent",
    "payment_withdrawal": "expressed_payment_withdrawal",
    "frustration": "expressed_frustration",
    "bug_report": "player_stated_bug_report",
    "feature_request": "expressed_feature_request",
}

BUSINESS_HYPOTHESES = {
    "performance": "possible satisfaction and retention relevance",
    "bugs_stability": "possible satisfaction and retention relevance",
    "fair_play_integrity": "possible trust, satisfaction, and retention relevance",
    "daily_commitment": "possible engagement and retention relevance",
    "grind": "possible engagement and retention relevance",
    "difficulty": "possible onboarding and retention relevance",
    "onboarding": "possible acquisition, early engagement, and retention relevance",
    "monetisation": "possible monetisation trust and payment relevance",
    "gacha": "possible monetisation trust and payment relevance",
    "controls": "possible accessibility and satisfaction relevance",
    "account_service": "possible trust and retention relevance",
    "story": "possible engagement and satisfaction relevance",
    "gameplay": "possible engagement and satisfaction relevance",
    "graphics": "possible satisfaction and acquisition relevance",
    "audio_music": "possible satisfaction relevance",
}


def _finding_id(evidence_id: str, topic: str) -> str:
    raw = json.dumps([evidence_id, topic], separators=(",", ":"))
    return f"analyst_{hashlib.sha256(raw.encode()).hexdigest()[:20]}"


def _complaint_by_topic(snapshot: IntelligenceCoreSnapshot) -> dict[str, list[Insight]]:
    values = {}
    for insight in snapshot.insight_bundle.player_insights:
        if insight.insight_type.value != "complaint":
            continue
        for topic in insight.taxonomy_nodes:
            values.setdefault(topic, []).append(insight)
    return values


def _priority_for(
    topic: str,
    evidence_id: str,
    complaints: dict[str, list[Insight]],
) -> dict | None:
    for insight in complaints.get(topic, []):
        if evidence_id in insight.supporting_evidence_ids and insight.priority:
            return insight.priority
    return None


def _stage(
    status: Literal["observed", "inferred", "expressed_intent", "hypothesis"],
    value: str,
    evidence_id: str,
    caveat: str | None = None,
) -> AnalystStage:
    return AnalystStage(
        status=status,
        value=value,
        evidence_ids=[evidence_id],
        caveat=caveat,
    )


def _finding(
    evidence: EvidenceItem,
    annotation: AnalysisAnnotation,
    complaints: dict[str, list[Insight]],
) -> AnalystFinding:
    evidence_id = evidence.evidence_id
    topic = annotation.primary_topic
    explicit = [
        _stage(
            "observed",
            request,
            evidence_id,
            "This is a player-stated request, not proof that the requested solution is optimal.",
        )
        for request in annotation.explicit_feature_requests
    ]
    opportunities = [
        _stage(
            "inferred",
            f"Investigate how to meet the underlying need: {need}.",
            evidence_id,
            "This opportunity is inferred from public player evidence.",
        )
        for need in annotation.underlying_needs
    ]
    opportunities.extend(
        _stage(
            "observed",
            f"Evaluate the player's explicit request: {request}",
            evidence_id,
            "Observed as a request only; solution value is not established.",
        )
        for request in annotation.explicit_feature_requests
    )
    hypothesis = BUSINESS_HYPOTHESES.get(topic)
    business = (
        [
            _stage(
                "hypothesis",
                hypothesis,
                evidence_id,
                "Public UGC does not establish behavioural impact or causality; validate with authorised first-party data.",
            )
        ]
        if hypothesis
        else []
    )
    return AnalystFinding(
        finding_id=_finding_id(evidence_id, topic),
        evidence=_stage("observed", " ".join(evidence.original_text.split())[:500], evidence_id),
        topic=_stage(
            "inferred",
            topic,
            evidence_id,
            f"Transparent taxonomy annotation {annotation.taxonomy_version}/{annotation.method.get('version')}",
        ),
        pain_points=[
            _stage(
                "inferred",
                value,
                evidence_id,
                "Pain point extracted from the player statement; severity/prevalence is not established.",
            )
            for value in annotation.pain_points
        ],
        underlying_needs=[
            _stage(
                "inferred",
                value,
                evidence_id,
                "Underlying need is an interpretation, not a direct player quote.",
            )
            for value in annotation.underlying_needs
        ],
        expressed_behaviour_signals=[
            _stage(
                "expressed_intent",
                BEHAVIOUR_LABELS.get(value, f"expressed_{value}"),
                evidence_id,
                "This labels what the player stated; it is not observed behaviour.",
            )
            for value in annotation.behaviour_signals
        ],
        possible_business_relevance=business,
        product_opportunities=opportunities,
        explicit_feature_requests=explicit,
        priority=_priority_for(topic, evidence_id, complaints),
    )


def build_analyst_report(snapshot: IntelligenceCoreSnapshot) -> AnalystReport:
    evidence = snapshot.evidence_by_id
    complaints = _complaint_by_topic(snapshot)
    complaint_evidence = {
        evidence_id
        for values in complaints.values()
        for insight in values
        for evidence_id in insight.supporting_evidence_ids
    }
    findings = []
    for annotation in snapshot.annotations:
        item = evidence.get(annotation.evidence_id)
        if item is None:
            continue
        actionable = bool(
            annotation.pain_points
            or annotation.underlying_needs
            or annotation.behaviour_signals
            or annotation.explicit_feature_requests
            or item.evidence_id in complaint_evidence
        )
        if actionable:
            findings.append(_finding(item, annotation, complaints))
    findings.sort(
        key=lambda value: (
            -(value.priority or {}).get("total_0_to_12", -1),
            value.topic.value,
            value.evidence.evidence_ids[0],
        )
    )
    gaps = []
    if not findings:
        gaps.append("No actionable evidence chain met the current transparent rules.")
    if not any(value.expressed_behaviour_signals for value in findings):
        gaps.append("No explicit player behaviour-intent statement was detected in the actionable sample.")
    if not any(value.underlying_needs for value in findings):
        gaps.append("No underlying need could be inferred reliably from the actionable sample.")
    gaps.append("No authorised observed-behaviour or retention dataset is joined; business relevance remains hypothesis only.")
    return AnalystReport(
        game_id=snapshot.game.game_id,
        game_title=snapshot.game.canonical_title,
        findings=findings,
        research_gaps=gaps,
        limitations=[
            "Analysis uses the public corpus only.",
            "Public discussion is self-selected and cannot estimate prevalence or causal business impact.",
            "Priority is a transparent decision-support signal, not a causal estimate.",
        ],
    )


def render_analyst_markdown(report: AnalystReport) -> str:
    lines = [
        f"# Analyst Mode — {report.game_title}",
        "",
        "- Data scope: public corpus only",
        "- Observed behaviour data available: no",
        f"- Priority: {report.priority_disclaimer}",
        "",
        "## Evidence → Product Insight chains",
        "",
    ]
    if not report.findings:
        lines.append("No actionable evidence chain met the current transparent rules.")
    for value in report.findings:
        lines.extend(
            [
                f"### {value.topic.value}",
                "",
                f"- **Observed evidence:** {value.evidence.value}",
                f"  - Evidence: `{value.evidence.evidence_ids[0]}`",
                f"- **Inferred topic:** {value.topic.value}",
            ]
        )
        for point in value.pain_points:
            lines.append(f"- **Inferred pain point:** {point.value}")
        for need in value.underlying_needs:
            lines.append(f"- **Inferred underlying need:** {need.value}")
        for signal in value.expressed_behaviour_signals:
            lines.append(f"- **Expressed intent / player statement:** {signal.value}")
            lines.append("  - Not observed behaviour.")
        for business in value.possible_business_relevance:
            lines.append(f"- **Hypothesis — possible business relevance:** {business.value}")
            lines.append(f"  - {business.caveat}")
        for opportunity in value.product_opportunities:
            label = "Observed player request" if opportunity.status == "observed" else "Inferred product opportunity"
            lines.append(f"- **{label}:** {opportunity.value}")
        if value.priority:
            lines.append(f"- **Decision-support priority:** `{json.dumps(value.priority, ensure_ascii=False, sort_keys=True)}`")
        lines.append("")
    lines.extend(["## Research gaps", ""])
    for value in report.research_gaps:
        lines.append(f"- {value}")
    lines.extend(["", "> Possible business relevance is a hypothesis. This report does not claim that a topic causes churn, revenue change, or observed player behaviour.", ""])
    return "\n".join(lines)
