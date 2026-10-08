from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from gamepulse.corpus import CorpusBuilder
from gamepulse.evidence import EvidenceStore
from gamepulse.insights import (
    DECISION_SUPPORT_DISCLAIMER,
    build_coverage_report,
    generate_insights,
    render_insight_report,
    validate_insight_integrity,
)
from gamepulse.intelligence import annotate_corpus, annotate_evidence
from gamepulse.models import (
    CollectionRun,
    EvidenceItem,
    FactRecord,
    GameEntity,
    Provenance,
    QueryPlan,
    SourceRunStatus,
)


NOW = datetime(2026, 10, 3, tzinfo=timezone.utc)


def game() -> GameEntity:
    return GameEntity(
        game_id="game_insights",
        canonical_title="Example Game",
        original_title="Example Game",
        localized_titles={"en": "Example Game", "zh-CN": "示例游戏"},
        external_ids={"steam_app_id": "1"},
        developers=["Example Studio"],
        publishers=["Example Publisher"],
        resolution_status="resolved",
        resolution_confidence=1,
        resolution_evidence_ids=["ev_identity"],
        resolved_at=NOW,
        genres=["action"],
    )


def query(source: str, query_id: str, language: str = "en") -> QueryPlan:
    return QueryPlan(
        query_id=query_id,
        run_id="run_insights",
        game_id="game_insights",
        source=source,
        language=language,
        intent="performance",
        query_text=f"{source} Example Game performance",
        alias_ids=["alias_example"],
        disambiguators=[],
        expected_evidence_kind="review" if source == "steam" else "comment",
        generated_at=NOW,
    )


def run() -> CollectionRun:
    plans = [
        query("steam", "query_steam"),
        query("bilibili", "query_bilibili", "zh-CN"),
        query("official", "query_official"),
    ]
    return CollectionRun(
        run_id="run_insights",
        request_hash="request-insights",
        game_ids=["game_insights"],
        query_plans=plans,
        code_version="test",
        config_version="test",
        taxonomy_version="1.0.0",
        started_at=NOW,
        ended_at=NOW,
        source_status={
            "steam": SourceRunStatus(status="collected", queries_attempted=1),
            "bilibili": SourceRunStatus(status="collected", queries_attempted=1),
            "official": SourceRunStatus(status="collected", queries_attempted=1),
            "reddit": SourceRunStatus(
                status="unavailable",
                queries_attempted=1,
                error_code="missing_credentials",
                reason="Reddit credentials not configured",
            ),
        },
    )


def evidence(
    evidence_id: str,
    source: str,
    text: str,
    *,
    query_id: str,
    recommended: bool | None,
    language: str,
    kind: str = "review",
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        game_id="game_insights",
        evidence_kind=kind,
        access_scope="public",
        dataset_id=None,
        source=source,
        source_content_id=evidence_id.removeprefix("ev_"),
        source_url=f"https://example.test/{source}/{evidence_id}",
        source_reference=None,
        title=None,
        original_text=text,
        normalized_text=None,
        language=language,
        published_at=NOW,
        retrieved_at=NOW,
        run_id="run_insights",
        query_id=query_id,
        matched_alias_ids=["alias_example"],
        retrieval_method="official_feed" if kind == "fact_source" else "public_endpoint",
        relevance_label="relevant",
        relevance_score=1,
        relevance_reasons=["fixture"],
        relevance_method_version="fixture-v1",
        recommended=recommended,
        platform=source,
        source_metadata={},
        provenance=Provenance(
            source_class="official" if kind == "fact_source" else (
                "platform_store" if source == "steam" else "public_community"
            ),
            collector_version="fixture-v1",
            content_checksum=f"checksum-{evidence_id}",
        ),
    )


def fixture_data():
    positive = evidence(
        "ev_steam_positive",
        "steam",
        "FPS is smooth and performance is great.",
        query_id="query_steam",
        recommended=True,
        language="en",
    )
    negative = evidence(
        "ev_bilibili_negative",
        "bilibili",
        "新版本更新后掉帧卡顿，表现很糟糕。",
        query_id="query_bilibili",
        recommended=None,
        language="zh-CN",
        kind="comment",
    )
    request = evidence(
        "ev_steam_request",
        "steam",
        "Please add better graphics settings; the FPS is terrible.",
        query_id="query_steam",
        recommended=False,
        language="en",
    )
    official = evidence(
        "ev_official_fact",
        "official",
        "Official platform support metadata",
        query_id="query_official",
        recommended=None,
        language="en",
        kind="fact_source",
    )
    fact = FactRecord(
        fact_id="fact_windows",
        game_id="game_insights",
        fact_type="platform_support",
        value=True,
        platform="Windows",
        source_evidence_id="ev_official_fact",
        source_authority="official",
        verification_status="verified",
        confidence=1,
        retrieved_at=NOW,
    )
    return [positive, negative, request, official], fact


class InsightEngineTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.store = EvidenceStore(root / "evidence.sqlite3")
        self.builder = CorpusBuilder(self.store, root / "raw")
        self.output_root = root
        items, fact = fixture_data()
        self.items = items
        self.fact = fact
        self.ugc = [item for item in items if item.evidence_kind.value in {"review", "comment"}]
        self.annotations = annotate_corpus(self.ugc, game())
        self.build_result = self.builder.build(run(), items, facts=[fact])
        self.bundle = generate_insights(
            "game_insights",
            items,
            self.annotations,
            [fact],
            self.build_result.run,
            source_exclusions={"bilibili": {"empty_or_deleted": 2}},
            generated_at=NOW,
        )

    def tearDown(self):
        self.directory.cleanup()

    def test_controvsery_has_two_distinguishable_positions(self):
        controversy = next(
            insight for insight in self.bundle.player_insights
            if insight.insight_type.value == "controversy" and "performance" in insight.taxonomy_nodes
        )
        self.assertTrue(controversy.supporting_evidence_ids)
        self.assertTrue(controversy.challenging_evidence_ids)
        self.assertIn("positive", controversy.sample_scope["sentiment_positions"])
        self.assertIn("negative", controversy.sample_scope["sentiment_positions"])

    def test_mixed_only_evidence_is_downgraded_to_open_research_gap(self):
        mixed_item = evidence(
            "ev_mixed",
            "bilibili",
            "Performance is great but FPS stutter is terrible.",
            query_id="query_bilibili",
            recommended=None,
            language="en",
            kind="comment",
        )
        mixed_annotation = annotate_evidence(mixed_item, game())
        result = generate_insights(
            "game_insights",
            [mixed_item],
            [mixed_annotation],
            [],
            run(),
            generated_at=NOW,
        )
        self.assertFalse(any(value.insight_type.value == "controversy" for value in result.player_insights))
        gap = next(value for value in result.player_insights if value.insight_type.value == "research_gap")
        self.assertIn("open question", gap.statement)

    def test_unavailable_source_is_visible_but_not_priority_negative_evidence(self):
        reddit = next(value for value in self.bundle.coverage.sources if value.source == "reddit")
        self.assertEqual(reddit.status, "unavailable")
        self.assertEqual(reddit.reason, "Reddit credentials not configured")
        complaint = next(
            value for value in self.bundle.player_insights
            if value.insight_type.value == "complaint" and "performance" in value.taxonomy_nodes
        )
        breadth = complaint.priority["components"]["source_breadth"]
        self.assertNotIn("reddit", breadth["eligible_collected_sources"])
        self.assertNotIn("reddit", breadth["represented_collected_sources"])

    def test_source_native_and_inferred_sentiment_methods_are_labelled(self):
        controversy = next(value for value in self.bundle.player_insights if value.insight_type.value == "controversy")
        methods = controversy.sample_scope["sentiment_methods"]
        self.assertGreater(methods["source_native_recommendation"], 0)
        self.assertGreater(methods["inferred_bilingual_lexicon"], 0)

    def test_priority_has_explicit_components_and_noncausal_disclaimer(self):
        complaint = next(value for value in self.bundle.player_insights if value.insight_type.value == "complaint")
        self.assertEqual(
            set(complaint.priority["components"]),
            {"volume", "negative_share", "momentum", "source_breadth"},
        )
        self.assertEqual(complaint.priority["disclaimer"], DECISION_SUPPORT_DISCLAIMER)

    def test_opportunity_distinguishes_explicit_request_and_inferred_need(self):
        opportunities = [
            value for value in self.bundle.player_insights if value.insight_type.value == "opportunity"
        ]
        origins = {value.opportunity_origin for value in opportunities}
        self.assertIn("explicit_request", origins)
        self.assertIn("inferred_need", origins)
        explicit = next(value for value in opportunities if value.opportunity_origin == "explicit_request")
        self.assertIn("Please add better graphics settings", explicit.statement)

    def test_coverage_lists_languages_dates_and_exclusions(self):
        self.assertEqual(self.bundle.coverage.languages, {"en": 3, "zh-CN": 1})
        self.assertEqual(self.bundle.coverage.date_start, NOW)
        bilibili = next(value for value in self.bundle.coverage.sources if value.source == "bilibili")
        self.assertEqual(bilibili.exclusions, {"empty_or_deleted": 2})
        self.assertEqual(self.bundle.coverage.excluded_from_analysis["retrieval:empty_or_deleted"], 2)

    def test_every_insight_and_fact_link_resolves(self):
        validate_insight_integrity(self.bundle, self.store)
        for insight in self.bundle.player_insights:
            ids = [*insight.supporting_evidence_ids, *insight.challenging_evidence_ids]
            self.assertTrue(ids)
            self.assertTrue(all(self.store.get_evidence(value) for value in ids))
        self.assertEqual(self.store.get_evidence(self.fact.source_evidence_id).source, "official")

    def test_integrity_fails_for_missing_evidence(self):
        broken = self.bundle.model_copy(deep=True)
        broken.player_insights[0].supporting_evidence_ids = ["ev_missing"]
        with self.assertRaisesRegex(ValueError, "unresolved evidence links"):
            validate_insight_integrity(broken, self.store)

    def test_report_links_back_to_original_source_and_separates_layers(self):
        output = render_insight_report(self.bundle, self.store, self.output_root / "report.md")
        report = output.read_text(encoding="utf-8")
        self.assertIn("## Official facts (Fact Layer)", report)
        self.assertIn("## Player insights (Player Evidence Layer)", report)
        self.assertIn("https://example.test/steam/ev_steam_positive", report)
        self.assertIn("Original source/reference", report)
        self.assertIn("| Duplicates |", report)
        self.assertIn("| Exclusions |", report)
        self.assertIn("Fact", report)
        self.assertIn("Player Evidence", report)
        self.assertIn(DECISION_SUPPORT_DISCLAIMER, report)

    def test_fact_and_player_records_are_not_merged(self):
        self.assertEqual(self.bundle.layer, "player_evidence")
        self.assertEqual(self.bundle.facts, [self.fact])
        self.assertFalse(
            any(self.fact.source_evidence_id in insight.supporting_evidence_ids for insight in self.bundle.player_insights)
        )

    def test_coverage_store_count_agreement(self):
        self.assertEqual(
            self.bundle.coverage.relevant_corpus_size,
            len(self.store.query_relevant_ugc("game_insights")),
        )


if __name__ == "__main__":
    unittest.main()
