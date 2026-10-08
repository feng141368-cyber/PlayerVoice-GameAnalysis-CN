"""Normalized corpus construction over the local Evidence Store."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

import pandas as pd
from pydantic import Field

from .compatibility import normalized_voice_row_to_evidence
from .evidence import COMMUNITY_KINDS, EvidenceStore, UpsertSummary
from .models import (
    CollectionRun,
    ContractModel,
    EvidenceItem,
    FactRecord,
    SourceRunStatus,
)


CORPUS_BUILDER_VERSION = "corpus-builder-v1"


class CorpusBuildResult(ContractModel):
    run: CollectionRun
    upsert: UpsertSummary
    snapshot_references: list[str]
    relevant_items: int = Field(ge=0)
    ambiguous_items: int = Field(ge=0)
    irrelevant_items: int = Field(ge=0)
    pending_items: int = Field(ge=0)


class CorpusBuilder:
    def __init__(self, store: EvidenceStore, raw_root: Path):
        self.store = store
        self.raw_root = raw_root

    def build(
        self,
        run: CollectionRun,
        evidence: Iterable[EvidenceItem],
        *,
        facts: Iterable[FactRecord] = (),
        owner_scope: str | None = None,
    ) -> CorpusBuildResult:
        items = list(evidence)
        for item in items:
            if item.run_id != run.run_id:
                raise ValueError(f"evidence {item.evidence_id} belongs to {item.run_id}, not {run.run_id}")
            if item.game_id not in run.game_ids:
                raise ValueError(f"evidence {item.evidence_id} game is outside the run scope")

        snapshot_paths, persisted_items = self._write_snapshots(run, items)
        summary = self.store.upsert_evidence(
            persisted_items,
            query_plans=run.query_plans,
            owner_scope=owner_scope,
        )
        fact_items = list(facts)
        if fact_items:
            self.store.upsert_facts(fact_items)

        source_counts: dict[str, Counter[str]] = defaultdict(Counter)
        source_identities: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for item in persisted_items:
            # Fact evidence retains its original platform source for traceback,
            # but belongs to the separate official/Fact Layer coverage bucket.
            # Counting it as both a Steam community item and an official item
            # would make the run manifest disagree with adapter retrieval totals.
            status_source = (
                "official" if item.evidence_kind.value == "fact_source" else item.source
            )
            source_counts[status_source][item.relevance_label.value] += 1
            source_identities[status_source].append((item.source, item.source_content_id))

        statuses = dict(run.source_status)
        for source, counts in source_counts.items():
            current = statuses.get(source) or SourceRunStatus(status="collected")
            duplicate_count = len(source_identities[source]) - len(set(source_identities[source]))
            statuses[source] = current.model_copy(
                update={
                    "items_retrieved": sum(counts.values()),
                    "items_relevant": counts["relevant"],
                    "items_ambiguous": counts["ambiguous"],
                    "items_irrelevant": counts["irrelevant"],
                    "duplicates": max(current.duplicates, duplicate_count),
                }
            )
        stored_run = run.model_copy(update={"source_status": statuses})
        self.store.save_run(stored_run)

        label_counts = Counter(
            item.relevance_label.value
            for item in persisted_items
            if item.evidence_kind.value in COMMUNITY_KINDS
        )
        return CorpusBuildResult(
            run=stored_run,
            upsert=summary,
            snapshot_references=sorted(snapshot_paths),
            relevant_items=label_counts["relevant"],
            ambiguous_items=label_counts["ambiguous"],
            irrelevant_items=label_counts["irrelevant"],
            pending_items=label_counts["pending"],
        )

    def _write_snapshots(
        self,
        run: CollectionRun,
        items: list[EvidenceItem],
    ) -> tuple[list[str], list[EvidenceItem]]:
        grouped: dict[tuple[str, str, str], list[EvidenceItem]] = defaultdict(list)
        for item in items:
            dataset = item.dataset_id or "public"
            grouped[(item.access_scope.value, dataset, item.source)].append(item)

        snapshot_by_group: dict[tuple[str, str, str], str] = {}
        paths: list[str] = []
        for (scope, dataset, source), source_items in grouped.items():
            safe_source = re.sub(r"[^a-z0-9_-]+", "-", source.casefold()).strip("-") or "source"
            if scope == "private":
                relative = Path("private") / dataset / run.run_id / f"{safe_source}.jsonl"
            else:
                relative = Path("public") / run.run_id / f"{safe_source}.jsonl"
            path = self.raw_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "".join(
                    json.dumps(item.to_dict(), ensure_ascii=False, sort_keys=True) + "\n"
                    for item in source_items
                ),
                encoding="utf-8",
            )
            reference = str(relative.as_posix())
            snapshot_by_group[(scope, dataset, source)] = reference
            paths.append(reference)

        persisted: list[EvidenceItem] = []
        for item in items:
            key = (item.access_scope.value, item.dataset_id or "public", item.source)
            provenance = item.provenance.model_copy(
                update={"raw_snapshot_reference": snapshot_by_group[key]}
            )
            persisted.append(item.model_copy(update={"provenance": provenance}))
        return paths, persisted

    def default_public_corpus(self, game_id: str) -> list[EvidenceItem]:
        return self.store.query_relevant_ugc(game_id)

    def ambiguous_review_queue(self, game_id: str | None = None) -> list[EvidenceItem]:
        return self.store.query_ambiguous(game_id)


def import_legacy_voice_sample(
    csv_path: Path,
    builder: CorpusBuilder,
    run: CollectionRun,
) -> CorpusBuildResult:
    """Validate and import the existing normalized sample through the new store."""

    frame = pd.read_csv(csv_path)
    if frame.empty:
        raise ValueError("legacy voice sample is empty")
    if len(run.game_ids) != 1:
        raise ValueError("legacy sample import requires one game in the run")
    items = [
        normalized_voice_row_to_evidence(
            row,
            game_id=run.game_ids[0],
            run_id=run.run_id,
        )
        for row in frame.to_dict(orient="records")
    ]
    return builder.build(run, items)
