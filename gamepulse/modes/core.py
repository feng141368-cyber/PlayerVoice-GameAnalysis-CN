"""Read-only Intelligence Core snapshots shared by every Mode."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from pydantic import Field, model_validator

from ..evidence import EvidenceStore
from ..insights import InsightBundle, validate_insight_integrity
from ..models import AnalysisAnnotation, ContractModel, EvidenceItem, FactRecord, GameEntity
from ..voice_slice import VoiceSliceResult
from .contracts import EvidenceReference


class IntelligenceCoreSnapshot(ContractModel):
    game: GameEntity
    facts: list[FactRecord]
    evidence: list[EvidenceItem]
    annotations: list[AnalysisAnnotation]
    insight_bundle: InsightBundle
    source_directory: str

    @model_validator(mode="after")
    def validate_shared_core(self) -> "IntelligenceCoreSnapshot":
        if self.insight_bundle.game_id != self.game.game_id:
            raise ValueError("Insight bundle and GameEntity identity differ")
        evidence_ids = {item.evidence_id for item in self.evidence}
        annotation_ids = {item.evidence_id for item in self.annotations}
        missing_annotations = sorted(
            item.evidence_id
            for item in self.evidence
            if item.evidence_kind.value in {"review", "post", "comment", "video_comment", "forum_thread", "forum_reply"}
            and item.relevance_label.value == "relevant"
            and item.evidence_id not in annotation_ids
        )
        if missing_annotations:
            raise ValueError(f"snapshot has relevant evidence without annotation: {missing_annotations[0]}")
        for insight in self.insight_bundle.player_insights:
            linked = [
                *insight.supporting_evidence_ids,
                *insight.challenging_evidence_ids,
                *insight.context_evidence_ids,
            ]
            if not set(linked).issubset(evidence_ids):
                raise ValueError(f"snapshot cannot resolve Insight {insight.insight_id}")
        return self

    @property
    def annotation_by_evidence(self) -> dict[str, AnalysisAnnotation]:
        return {item.evidence_id: item for item in self.annotations}

    @property
    def evidence_by_id(self) -> dict[str, EvidenceItem]:
        return {item.evidence_id: item for item in self.evidence}


def load_core_snapshot(output_directory: Path) -> IntelligenceCoreSnapshot:
    """Load one completed Issue 10 result without rerunning retrieval/analysis."""

    result_path = output_directory / "voice_slice_result.json"
    if not result_path.exists():
        raise ValueError(f"missing voice slice result: {result_path}")
    result = VoiceSliceResult.model_validate_json(result_path.read_text(encoding="utf-8"))
    if result.foundation.resolution.game is None:
        raise ValueError("voice slice does not contain a resolved game")
    store = EvidenceStore(output_directory / "evidence.sqlite3")
    validate_insight_integrity(result.insights, store)
    annotation_path = output_directory / "annotations.jsonl"
    annotations = [
        AnalysisAnnotation.model_validate(json.loads(line))
        for line in annotation_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return IntelligenceCoreSnapshot(
        game=result.foundation.resolution.game,
        facts=result.insights.facts,
        evidence=store.query_public(game_id=result.insights.game_id),
        annotations=annotations,
        insight_bundle=result.insights,
        source_directory=str(output_directory),
    )


def evidence_references(
    snapshots: Iterable[IntelligenceCoreSnapshot],
    evidence_ids: Iterable[str],
) -> list[EvidenceReference]:
    wanted = set(evidence_ids)
    references: dict[str, EvidenceReference] = {}
    for snapshot in snapshots:
        fact_evidence = {fact.source_evidence_id for fact in snapshot.facts}
        for item in snapshot.evidence:
            if item.evidence_id not in wanted:
                continue
            references[item.evidence_id] = EvidenceReference(
                evidence_id=item.evidence_id,
                game_id=item.game_id,
                layer="fact" if item.evidence_id in fact_evidence else "player_evidence",
                source=item.source,
                source_url=item.source_url,
                source_reference=item.source_reference,
                excerpt=" ".join(item.original_text.split())[:280],
            )
    unresolved = sorted(wanted.difference(references))
    if unresolved:
        raise ValueError(f"Mode output contains unresolved evidence: {', '.join(unresolved)}")
    return [references[value] for value in sorted(references)]
