from __future__ import annotations

import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from gamepulse.models import (
    AnalysisAnnotation,
    CollectionRun,
    EvidenceItem,
    FactRecord,
    GameAlias,
    GameEntity,
    Insight,
    PatchRecord,
    PrivateDataset,
    Provenance,
    QueryPlan,
)


NOW = datetime(2026, 9, 29, tzinfo=timezone.utc)


def round_trip(test: unittest.TestCase, model):
    rebuilt = type(model).from_dict(model.to_dict())
    test.assertEqual(rebuilt, model)


class DomainModelTests(unittest.TestCase):
    def setUp(self):
        self.provenance = Provenance(
            source_class="official",
            collector_version="test-v1",
            content_checksum="abc123",
        )
        self.query = QueryPlan(
            query_id="query_1",
            run_id="run_1",
            game_id="game_1",
            source="official_site",
            language="en",
            intent="general",
            query_text="Example Game official requirements",
            alias_ids=["alias_1"],
            disambiguators=["Example Studio"],
            expected_evidence_kind="fact",
            generated_at=NOW,
        )

    def test_every_model_round_trips(self):
        models = [
            GameEntity(
                game_id="game_1", canonical_title="Example Game", original_title="Example Game",
                localized_titles={"en": "Example Game"}, external_ids={"wikidata_id": "Q1"},
                developers=["Example Studio"], publishers=["Example Publisher"],
                resolution_status="resolved", resolution_confidence=0.99,
                resolution_evidence_ids=["ev_identity"], resolved_at=NOW,
            ),
            GameAlias(
                alias_id="alias_1", game_id="game_1", text="EG", normalized_text="eg", language="en",
                alias_type="abbreviation", source_evidence_ids=["ev_alias"], source_platforms=["reddit"],
                confidence=0.8, ambiguity="medium", validation_status="scoped_only",
                search_enabled=True, standalone_search_safe=False,
            ),
            FactRecord(
                fact_id="fact_1", game_id="game_1", fact_type="developer", value="Example Studio",
                source_evidence_id="ev_fact", source_authority="official",
                verification_status="verified", confidence=1, retrieved_at=NOW,
            ),
            self.query,
            EvidenceItem(
                evidence_id="ev_1", game_id="game_1", evidence_kind="official", access_scope="public",
                dataset_id=None, source="official_site", source_content_id="page-1",
                source_url="https://example.com/game", original_text="Official game page", language="en",
                published_at=None, retrieved_at=NOW, run_id="run_1", query_id="query_1",
                matched_alias_ids=["alias_1"], retrieval_method="official_feed",
                relevance_label="relevant", relevance_score=1, relevance_reasons=["official identity page"],
                provenance=self.provenance,
            ),
            AnalysisAnnotation(
                annotation_id="annotation_1", evidence_id="ev_1", taxonomy_version="1.0",
                primary_topic="core.gameplay", secondary_topics=[], sentiment_label="neutral",
                pain_points=[], underlying_needs=[], explicit_feature_requests=[], behaviour_signals=[],
                analysis_confidence=0.9, method={"name": "rules", "version": "1"},
                requires_human_review=False,
            ),
            Insight(
                insight_id="insight_1", scope_type="game", scope_ids=["game_1"], mode="player",
                insight_type="fact_summary", statement="The game supports PC.", taxonomy_nodes=["platforms"],
                confidence=1, supporting_evidence_ids=["ev_1"], challenging_evidence_ids=[],
                context_evidence_ids=[], sample_scope={"sources": 1}, uncertainty=[], generated_at=NOW,
            ),
            PatchRecord(
                patch_id="patch_1", game_id="game_1", release_type="patch", version="1.1",
                title="Patch 1.1", published_at=NOW, effective_at=NOW, platforms=["PC"], territories=["global"],
                change_items=[{"text": "Fixed crash", "taxonomy_nodes": ["technical.stability"]}],
                official_evidence_ids=["ev_patch"],
            ),
            PrivateDataset(
                dataset_id="dataset_1", owner_scope="workspace_1", name="Authorised survey", source_type="survey",
                authorisation_attested=True, schema_mapping={"answer": "original_text"},
                allowed_modes=["analyst"], retention_policy={"days": 30}, created_at=NOW, status="ready",
            ),
            CollectionRun(
                run_id="run_1", request_hash="hash", game_ids=["game_1"], query_plans=[self.query],
                code_version="0.3", config_version="1", taxonomy_version="1.0", started_at=NOW,
                source_status={"official_site": {"status": "collected", "queries_attempted": 1, "items_retrieved": 1}},
            ),
        ]
        for model in models:
            with self.subTest(model=type(model).__name__):
                round_trip(self, model)

    def test_high_ambiguity_alias_cannot_be_standalone_safe(self):
        with self.assertRaises(ValidationError):
            GameAlias(
                alias_id="alias_1", game_id="game_1", text="LOL", normalized_text="lol", language="en",
                alias_type="abbreviation", source_evidence_ids=["ev_1"], source_platforms=["reddit"],
                confidence=0.9, ambiguity="high", validation_status="scoped_only",
                search_enabled=True, standalone_search_safe=True,
            )

    def test_rejected_alias_cannot_be_search_enabled(self):
        with self.assertRaises(ValidationError):
            GameAlias(
                alias_id="alias_1", game_id="game_1", text="bad", normalized_text="bad", language=None,
                alias_type="community_nickname", source_evidence_ids=[], source_platforms=[], confidence=0,
                ambiguity="high", validation_status="rejected", search_enabled=True, standalone_search_safe=False,
            )

    def test_private_evidence_requires_dataset(self):
        with self.assertRaises(ValidationError):
            EvidenceItem(
                evidence_id="ev_private", game_id="game_1", evidence_kind="survey_response",
                access_scope="private", dataset_id=None, source="survey", source_content_id="1",
                original_text="Private response", language="en", published_at=NOW, retrieved_at=NOW,
                run_id="run_1", matched_alias_ids=[], retrieval_method="user_upload",
                relevance_label="pending", relevance_reasons=[], provenance=self.provenance,
            )

    def test_insight_requires_evidence(self):
        with self.assertRaises(ValidationError):
            Insight(
                insight_id="insight_empty", scope_type="game", scope_ids=["game_1"], mode="analyst",
                insight_type="complaint", statement="Unsupported claim", taxonomy_nodes=[], confidence=0.5,
                supporting_evidence_ids=[], challenging_evidence_ids=[], context_evidence_ids=[],
                sample_scope={}, uncertainty=[], generated_at=NOW,
            )


if __name__ == "__main__":
    unittest.main()
