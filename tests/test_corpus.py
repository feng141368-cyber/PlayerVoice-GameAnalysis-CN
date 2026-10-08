from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from gamepulse.corpus import CorpusBuilder, import_legacy_voice_sample
from gamepulse.evidence import EVIDENCE_STORE_SCHEMA_VERSION, EvidenceStore
from gamepulse.models import (
    CollectionRun,
    EvidenceItem,
    FactRecord,
    PrivateDataset,
    Provenance,
    QueryPlan,
    SourceRunStatus,
)


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 3, tzinfo=timezone.utc)


def query(query_id: str, *, intent: str = "performance", source: str = "steam") -> QueryPlan:
    return QueryPlan(
        query_id=query_id,
        run_id="run_corpus",
        game_id="game_cs2",
        source=source,
        language="en",
        intent=intent,
        query_text=f"steam_app:730 intent:{intent}" if source == "steam" else f'"CS2" Counter-Strike 2 Valve {intent}',
        alias_ids=["alias_cs2"],
        disambiguators=["Counter-Strike 2", "Valve"],
        expected_evidence_kind="review" if source == "steam" else "post",
        generated_at=NOW,
    )


def run(*plans: QueryPlan, run_id: str = "run_corpus") -> CollectionRun:
    remapped = [plan.model_copy(update={"run_id": run_id}) for plan in plans]
    return CollectionRun(
        run_id=run_id,
        request_hash=f"request-{run_id}",
        game_ids=["game_cs2"],
        query_plans=remapped,
        code_version="test",
        config_version="test",
        taxonomy_version="1.0",
        started_at=NOW,
        ended_at=NOW,
        source_status={
            "steam": SourceRunStatus(status="collected", queries_attempted=1),
            "reddit": SourceRunStatus(
                status="unavailable",
                queries_attempted=1,
                error_code="missing_credentials",
                reason="credentials not configured",
            ),
        },
    )


def item(
    source: str,
    source_id: str,
    text: str,
    *,
    evidence_id: str | None = None,
    query_id: str | None = "query_performance",
    relevance: str = "relevant",
    access_scope: str = "public",
    dataset_id: str | None = None,
    retrieval_method: str = "public_endpoint",
    run_id: str = "run_corpus",
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id or f"ev_{source}_{source_id}",
        game_id="game_cs2",
        evidence_kind="review" if source == "steam" else "post",
        access_scope=access_scope,
        dataset_id=dataset_id,
        source=source,
        source_content_id=source_id,
        source_url=f"https://example.test/{source}/{source_id}",
        source_reference=None,
        title=None,
        original_text=text,
        normalized_text=None,
        language="en",
        published_at=NOW,
        retrieved_at=NOW,
        run_id=run_id,
        query_id=query_id,
        matched_alias_ids=["alias_cs2"] if query_id else [],
        retrieval_method=retrieval_method,
        relevance_label=relevance,
        relevance_score=0.9 if relevance == "relevant" else 0.4,
        relevance_reasons=["fixture"],
        relevance_method_version="fixture-v1",
        platform=source,
        source_metadata={"native": True},
        provenance=Provenance(
            source_class="user_provided" if access_scope == "private" else "public_community",
            collector_version="fixture-v1",
            content_checksum=f"checksum-{source}-{source_id}",
        ),
    )


def dataset() -> PrivateDataset:
    return PrivateDataset(
        dataset_id="dataset_private_1",
        owner_scope="workspace_alpha",
        name="Authorised research responses",
        source_type="research_dataset",
        authorisation_attested=True,
        schema_mapping={"text": "original_text"},
        allowed_modes=["analyst"],
        retention_policy={"days": 30},
        created_at=NOW,
        status="ready",
    )


class CorpusStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.store = EvidenceStore(root / "evidence.sqlite3")
        self.builder = CorpusBuilder(self.store, root / "raw")

    def tearDown(self):
        self.directory.cleanup()

    def test_schema_version_is_explicit(self):
        self.assertEqual(self.store.schema_version, EVIDENCE_STORE_SCHEMA_VERSION)

    def test_rerun_updates_same_source_item_instead_of_doubling(self):
        query_plan = query("query_performance")
        first = self.builder.build(run(query_plan), [item("steam", "r1", "First version")])
        updated = item("steam", "r1", "Edited version")
        second = self.builder.build(run(query_plan), [updated])
        self.assertEqual(first.upsert.inserted, 1)
        self.assertEqual(second.upsert.updated, 1)
        self.assertEqual(second.upsert.duplicates, 1)
        self.assertEqual(self.store.count(access_scope="public"), 1)
        self.assertEqual(self.store.get_evidence("ev_steam_r1").original_text, "Edited version")

    def test_cross_platform_same_text_stays_separate_but_shares_fingerprint(self):
        steam_plan = query("query_performance")
        reddit_plan = query("query_reddit", source="reddit")
        result = self.builder.build(
            run(steam_plan, reddit_plan),
            [
                item("steam", "same-1", "The update made performance worse"),
                item("reddit", "same-2", "The update made performance worse", query_id="query_reddit"),
            ],
        )
        self.assertEqual(result.upsert.inserted, 2)
        self.assertEqual(result.upsert.likely_cross_posts, 1)
        self.assertEqual(self.store.count(access_scope="public"), 2)
        duplicate = self.store.duplicate_info("ev_steam_same-1")
        self.assertEqual(duplicate["likely_cross_posts"][0]["source"], "reddit")

    def test_public_default_never_returns_private_evidence(self):
        self.store.register_private_dataset(dataset())
        self.store.upsert_evidence([item("steam", "public", "Public review")])
        private = item(
            "survey",
            "private",
            "Private response",
            access_scope="private",
            dataset_id="dataset_private_1",
            retrieval_method="user_upload",
        )
        self.store.upsert_evidence([private], owner_scope="workspace_alpha")
        self.assertEqual([value.source_content_id for value in self.store.query_public()], ["public"])
        self.assertEqual(
            [value.source_content_id for value in self.store.query_private(
                dataset_id="dataset_private_1", owner_scope="workspace_alpha"
            )],
            ["private"],
        )
        with self.assertRaises(PermissionError):
            self.store.query_private(dataset_id="dataset_private_1", owner_scope="workspace_beta")
        with self.assertRaises(PermissionError):
            self.store.get_evidence("ev_survey_private")

    def test_public_user_upload_is_rejected(self):
        uploaded = item(
            "upload",
            "unsafe",
            "Should be private",
            retrieval_method="user_upload",
        )
        with self.assertRaises(PermissionError):
            self.store.upsert_evidence([uploaded])

    def test_multiple_queries_deduplicate_one_player_item_and_keep_all_links(self):
        performance = query("query_performance")
        bugs = query("query_bugs", intent="bugs")
        first = item("steam", "multi", "Update caused FPS drops", query_id="query_performance")
        second = item("steam", "multi", "Update caused FPS drops", query_id="query_bugs")
        result = self.builder.build(run(performance, bugs), [first, second])
        self.assertEqual(result.upsert.inserted, 1)
        self.assertEqual(result.upsert.updated, 1)
        stored = self.store.get_evidence("ev_steam_multi")
        matched = stored.source_metadata["matched_queries"]
        self.assertEqual({value["intent"] for value in matched}, {"performance", "bugs"})
        self.assertEqual(self.store.count(), 1)

    def test_evidence_lookup_restores_original_and_provenance(self):
        query_plan = query("query_performance")
        result = self.builder.build(run(query_plan), [item("steam", "lookup", "Original player text")])
        stored = self.store.get_evidence("ev_steam_lookup")
        self.assertEqual(stored.original_text, "Original player text")
        self.assertEqual(stored.run_id, "run_corpus")
        self.assertEqual(stored.query_id, "query_performance")
        self.assertTrue(stored.provenance.raw_snapshot_reference)
        self.assertIn(stored.provenance.raw_snapshot_reference, result.snapshot_references)
        self.assertEqual(stored.source_url, "https://example.test/steam/lookup")

    def test_partial_source_failure_commits_success_and_truthful_manifest(self):
        query_plan = query("query_performance")
        result = self.builder.build(run(query_plan), [item("steam", "success", "A relevant review")])
        stored_run = self.store.get_run("run_corpus")
        self.assertEqual(stored_run.source_status["steam"].items_retrieved, 1)
        self.assertEqual(stored_run.source_status["steam"].items_relevant, 1)
        self.assertEqual(stored_run.source_status["reddit"].status.value, "unavailable")
        self.assertEqual(stored_run.source_status["reddit"].items_retrieved, 0)
        self.assertEqual(len(self.builder.default_public_corpus("game_cs2")), 1)
        self.assertEqual(result.relevant_items, 1)

    def test_fact_records_are_queryable_separately(self):
        fact = FactRecord(
            fact_id="fact_platform",
            game_id="game_cs2",
            fact_type="platform_support",
            value=True,
            platform="Windows",
            source_evidence_id="ev_fact_source",
            source_authority="platform_store",
            verification_status="verified",
            confidence=1,
            retrieved_at=NOW,
        )
        self.store.upsert_facts([fact])
        self.assertEqual(self.store.query_facts("game_cs2"), [fact])
        self.assertEqual(self.store.query_relevant_ugc("game_cs2"), [])

    def test_existing_327_record_sample_imports_and_validates(self):
        legacy_run = CollectionRun(
            run_id="run_legacy_import",
            request_hash="legacy-sample",
            game_ids=["game_tower_of_fantasy"],
            query_plans=[],
            code_version="test",
            config_version="legacy",
            taxonomy_version="1.0",
            started_at=NOW,
            ended_at=NOW,
            source_status={
                "steam": SourceRunStatus(status="collected"),
                "bilibili": SourceRunStatus(status="collected"),
            },
        )
        result = import_legacy_voice_sample(
            ROOT / "data/processed/voice.csv",
            self.builder,
            legacy_run,
        )
        self.assertEqual(result.upsert.inserted, 327)
        self.assertEqual(self.store.count(access_scope="public"), 327)
        self.assertEqual(result.pending_items, 327)
        self.assertEqual(self.builder.default_public_corpus("game_tower_of_fantasy"), [])


if __name__ == "__main__":
    unittest.main()
