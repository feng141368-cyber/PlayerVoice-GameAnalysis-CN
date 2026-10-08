from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from gamepulse.models import EvidenceItem, GameAlias, GameEntity, Provenance, RelevanceLabel
from gamepulse.relevance import (
    RelevanceSettings,
    evaluate_relevance,
    relevant_only,
    summarize_fixture_labels,
    write_review_queue,
)


NOW = datetime(2026, 10, 3, tzinfo=timezone.utc)


def game() -> GameEntity:
    return GameEntity(
        game_id="game_cs2",
        canonical_title="Counter-Strike 2",
        original_title="Counter-Strike 2",
        localized_titles={"en": "Counter-Strike 2", "zh-CN": "反恐精英2"},
        external_ids={"steam_app_id": "730"},
        developers=["Valve"],
        publishers=["Valve"],
        resolution_status="resolved",
        resolution_confidence=1,
        resolution_evidence_ids=["ev_identity"],
        resolved_at=NOW,
        platforms=["PC"],
    )


def aliases() -> list[GameAlias]:
    return [
        GameAlias(
            alias_id="alias_cs2",
            game_id="game_cs2",
            text="CS2",
            normalized_text="cs2",
            language="en",
            alias_type="abbreviation",
            source_evidence_ids=["ev_alias_cs2"],
            source_platforms=["steam", "reddit"],
            confidence=0.9,
            ambiguity="high",
            ambiguity_notes="Also Adobe Creative Suite 2 and other entities",
            validation_status="scoped_only",
            search_enabled=True,
            standalone_search_safe=False,
        ),
        GameAlias(
            alias_id="alias_cn",
            game_id="game_cs2",
            text="反恐精英2",
            normalized_text="反恐精英2",
            language="zh-CN",
            alias_type="localized_title",
            source_evidence_ids=["ev_alias_cn"],
            source_platforms=["official"],
            confidence=1,
            ambiguity="none",
            validation_status="validated",
            search_enabled=True,
            standalone_search_safe=True,
        ),
    ]


def evidence(
    text: str,
    *,
    source: str = "reddit",
    title: str | None = None,
    metadata: dict | None = None,
    suffix: str = "1",
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=f"ev_{suffix}",
        game_id="game_cs2",
        evidence_kind="review" if source == "steam" else "post",
        access_scope="public",
        dataset_id=None,
        source=source,
        source_content_id=suffix,
        source_url=f"https://example.test/{suffix}",
        source_reference=None,
        title=title,
        original_text=text,
        normalized_text=None,
        language="en",
        published_at=NOW,
        retrieved_at=NOW,
        run_id="run_relevance",
        query_id="query_relevance",
        matched_alias_ids=["alias_cs2"],
        retrieval_method="public_endpoint",
        relevance_label="pending",
        relevance_score=None,
        relevance_reasons=[],
        relevance_method_version=None,
        platform=source,
        source_metadata=metadata or {},
        provenance=Provenance(
            source_class="platform_store" if source == "steam" else "public_community",
            collector_version="fixture-v1",
            content_checksum=f"checksum-{suffix}",
        ),
    )


class RelevanceEngineTests(unittest.TestCase):
    def test_correct_steam_app_id_is_relevant_without_title_in_text(self):
        result = evaluate_relevance(
            evidence("The latest build stutters badly.", source="steam", metadata={"app_id": 730}),
            game(),
            aliases(),
        )
        self.assertEqual(result.decision.label, RelevanceLabel.RELEVANT)
        self.assertEqual(result.decision.score, 0.99)
        self.assertIn("source_native_id_match:steam_app_id=730", result.decision.reasons)

    def test_ambiguous_alias_only_is_never_relevant(self):
        result = evaluate_relevance(evidence("CS2 is terrible."), game(), aliases())
        self.assertEqual(result.decision.label, RelevanceLabel.AMBIGUOUS)
        self.assertIn("ambiguous_alias_without_independent_game_context", result.decision.reasons)
        self.assertEqual(result.decision.signals["matched_alias_ids"], ["alias_cs2"])

    def test_ambiguous_alias_with_game_specific_context_can_be_relevant(self):
        result = evaluate_relevance(
            evidence("CS2 update made my FPS worse on Mirage."),
            game(),
            aliases(),
            game_terms=["Mirage"],
        )
        self.assertEqual(result.decision.label, RelevanceLabel.RELEVANT)
        self.assertTrue(any(reason.startswith("game_term_match:Mirage") for reason in result.decision.reasons))
        self.assertTrue(any(reason.startswith("surrounding_context:") for reason in result.decision.reasons))

    def test_competing_native_entity_is_irrelevant(self):
        result = evaluate_relevance(
            evidence("CS2 performance guide", source="steam", metadata={"app_id": 949230}),
            game(),
            aliases(),
        )
        self.assertEqual(result.decision.label, RelevanceLabel.IRRELEVANT)
        self.assertIn("source_native_id_mismatch:steam_app_id=949230", result.decision.reasons)

    def test_competing_entity_name_is_negative_evidence(self):
        result = evaluate_relevance(
            evidence("CS2 road traffic mods for Cities: Skylines 2"),
            game(),
            aliases(),
            competing_entities=["Cities Skylines 2", "Cities: Skylines 2"],
        )
        self.assertEqual(result.decision.label, RelevanceLabel.IRRELEVANT)
        self.assertTrue(any(reason.startswith("competing_entity_match:") for reason in result.decision.reasons))

    def test_official_english_and_chinese_titles_are_relevant(self):
        english = evaluate_relevance(evidence("Counter-Strike 2 needs better frame pacing"), game(), aliases())
        chinese = evaluate_relevance(evidence("反恐精英2更新后有卡顿", suffix="2"), game(), aliases())
        self.assertEqual(english.decision.label, RelevanceLabel.RELEVANT)
        self.assertEqual(chinese.decision.label, RelevanceLabel.RELEVANT)

    def test_threshold_changes_are_configurable_and_method_versioned(self):
        item = evidence("Counter-Strike 2 needs better frame pacing")
        default = evaluate_relevance(item, game(), aliases())
        stricter = evaluate_relevance(
            item,
            game(),
            aliases(),
            settings=RelevanceSettings(relevant_threshold=0.9, ambiguous_threshold=0.25),
        )
        self.assertEqual(default.decision.label, RelevanceLabel.RELEVANT)
        self.assertEqual(stricter.decision.label, RelevanceLabel.AMBIGUOUS)
        self.assertNotEqual(default.decision.method_version, stricter.decision.method_version)
        self.assertEqual(stricter.evidence.relevance_method_version, stricter.decision.method_version)

    def test_sentiment_words_do_not_change_relevance(self):
        negative = evaluate_relevance(evidence("CS2 is terrible.", suffix="negative"), game(), aliases())
        positive = evaluate_relevance(evidence("CS2 is wonderful.", suffix="positive"), game(), aliases())
        self.assertEqual(negative.decision.score, positive.decision.score)
        self.assertEqual(negative.decision.label, positive.decision.label)

    def test_ambiguous_review_queue_writes_json_and_csv(self):
        ambiguous = evaluate_relevance(evidence("CS2 is terrible."), game(), aliases())
        relevant = evaluate_relevance(
            evidence("Counter-Strike 2 needs better frame pacing", suffix="relevant"),
            game(),
            aliases(),
        )
        with tempfile.TemporaryDirectory() as directory:
            json_path = Path(directory) / "review.json"
            csv_path = Path(directory) / "review.csv"
            self.assertEqual(write_review_queue([ambiguous, relevant], json_path), 1)
            self.assertEqual(write_review_queue([ambiguous, relevant], csv_path), 1)
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload[0]["evidence_id"], "ev_1")
            self.assertIn("relevance_method_version", csv_path.read_text(encoding="utf-8"))
        self.assertEqual(relevant_only([ambiguous, relevant]), [relevant.evidence])

    def test_fixture_precision_recall_summary_is_explicit(self):
        cases = [
            (evaluate_relevance(evidence("Counter-Strike 2 patch", suffix="a"), game(), aliases()), "relevant"),
            (evaluate_relevance(evidence("CS2 is terrible", suffix="b"), game(), aliases()), "ambiguous"),
            (evaluate_relevance(evidence("Unrelated cooking recipe", suffix="c"), game(), aliases()), "irrelevant"),
        ]
        summary = summarize_fixture_labels(cases)
        print(f"Relevance fixture precision={summary.precision:.2f}, recall={summary.recall:.2f}")
        self.assertEqual(summary.precision, 1)
        self.assertEqual(summary.recall, 1)


if __name__ == "__main__":
    unittest.main()
