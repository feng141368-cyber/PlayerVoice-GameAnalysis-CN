from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml
from pydantic import ValidationError

from gamepulse.compatibility import normalized_voice_row_to_evidence
from gamepulse.intelligence import (
    annotate_corpus,
    annotate_evidence,
    load_taxonomy,
    priority_eligible_topic,
    write_annotations_jsonl,
)
from gamepulse.models import EvidenceItem, GameEntity, Provenance


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 3, tzinfo=timezone.utc)


def game(*genres: str) -> GameEntity:
    return GameEntity(
        game_id="game_annotation",
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
        genres=list(genres),
    )


def evidence(text: str, *, suffix: str = "1", recommended: bool | None = None, language: str = "en") -> EvidenceItem:
    return EvidenceItem(
        evidence_id=f"ev_annotation_{suffix}",
        game_id="game_annotation",
        evidence_kind="review",
        access_scope="public",
        dataset_id=None,
        source="steam",
        source_content_id=suffix,
        source_url=f"https://example.test/{suffix}",
        source_reference=None,
        title=None,
        original_text=text,
        normalized_text=None,
        language=language,
        published_at=NOW,
        retrieved_at=NOW,
        run_id="run_annotation",
        query_id="query_annotation",
        matched_alias_ids=["alias_example"],
        retrieval_method="public_endpoint",
        relevance_label="relevant",
        relevance_score=0.9,
        relevance_reasons=["fixture"],
        relevance_method_version="fixture-v1",
        recommended=recommended,
        platform="steam",
        source_metadata={},
        provenance=Provenance(
            source_class="platform_store",
            collector_version="fixture-v1",
            content_checksum=f"checksum-{suffix}",
        ),
    )


class IntelligenceTests(unittest.TestCase):
    def test_taxonomy_loads_and_has_versioned_core(self):
        taxonomy = load_taxonomy()
        self.assertEqual(taxonomy.version, "1.1.0")
        self.assertIn("performance", {topic.id for topic in taxonomy.core_topics})
        self.assertIn("fair_play_integrity", {topic.id for topic in taxonomy.core_topics})
        self.assertTrue(taxonomy.config_hash)

    def test_taxonomy_duplicate_ids_fail_clearly(self):
        payload = yaml.safe_load((ROOT / "config/taxonomy.yaml").read_text(encoding="utf-8"))
        payload["core_topics"].append(dict(payload["core_topics"][0]))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "taxonomy.yaml"
            path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "duplicate taxonomy topic IDs"):
                load_taxonomy(path)

    def test_taxonomy_missing_labels_fail_clearly(self):
        payload = yaml.safe_load((ROOT / "config/taxonomy.yaml").read_text(encoding="utf-8"))
        del payload["core_topics"][0]["label_zh"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "taxonomy.yaml"
            path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
            with self.assertRaises(ValidationError):
                load_taxonomy(path)

    def test_review_can_have_combat_primary_and_controls_secondary(self):
        annotation = annotate_evidence(
            evidence("Combat, weapons and recoil feel great, but controller controls are frustrating."),
            game("action"),
        )
        self.assertEqual(annotation.primary_topic, "combat")
        self.assertIn("controls", annotation.secondary_topics)
        self.assertEqual(annotation.sentiment_label.value, "mixed")

    def test_performance_is_not_monetisation_for_passing_price_mention(self):
        annotation = annotate_evidence(
            evidence("FPS drops and stutter are terrible; at this price I expected smoother play."),
            game("action"),
        )
        self.assertEqual(annotation.primary_topic, "performance")
        self.assertIn("monetisation", annotation.secondary_topics)

    def test_fps_genre_mentions_are_not_performance_evidence(self):
        for index, text in enumerate(
            [
                "经典的 FPS 游戏，有趣。",
                "在其他 FPS games 达到中高段位以后再来玩。",
                "我没有 FPS 天赋。",
            ]
        ):
            with self.subTest(text=text):
                annotation = annotate_evidence(
                    evidence(text, suffix=f"fps-genre-{index}", language="zh-CN"),
                    game("shooter"),
                )
                self.assertNotIn(
                    "performance",
                    {annotation.primary_topic, *annotation.secondary_topics},
                )

    def test_numeric_or_degrading_fps_is_performance_evidence(self):
        for index, text in enumerate(
            [
                "The game only runs at 30 FPS.",
                "FPS drops after every update.",
                "更新后掉到 20 FPS。",
            ]
        ):
            with self.subTest(text=text):
                annotation = annotate_evidence(
                    evidence(text, suffix=f"fps-performance-{index}"),
                    game("shooter"),
                )
                self.assertEqual(annotation.primary_topic, "performance")

    def test_native_recommendation_is_preserved_when_sentiment_differs(self):
        source = evidence("The new patch is terrible and stutters constantly.", recommended=True)
        annotation = annotate_evidence(source, game("action"))
        self.assertEqual(annotation.sentiment_label.value, "negative")
        self.assertTrue(source.recommended)
        self.assertTrue(annotation.method["source_native_recommendation_preserved"])

    def test_gacha_extension_activates_only_for_gacha_game(self):
        text = evidence("The pity and limited banner rules are confusing.")
        active = annotate_evidence(text, game("gacha"))
        inactive = annotate_evidence(text, game("action"))
        active_topics = {active.primary_topic, *active.secondary_topics}
        inactive_topics = {inactive.primary_topic, *inactive.secondary_topics}
        self.assertTrue({"gacha.pity", "gacha.banner"}.intersection(active_topics))
        self.assertFalse(any(topic.startswith("gacha.") for topic in inactive_topics))

    def test_mmo_extension_activates_only_for_mmo_game(self):
        text = evidence("Raid matchmaking and guild queues take too long.")
        active = annotate_evidence(text, game("MMORPG"))
        inactive = annotate_evidence(text, game("action"))
        active_topics = {active.primary_topic, *active.secondary_topics}
        inactive_topics = {inactive.primary_topic, *inactive.secondary_topics}
        self.assertTrue(any(topic.startswith("mmo.") for topic in active_topics))
        self.assertFalse(any(topic.startswith("mmo.") for topic in inactive_topics))

    def test_core_topics_remain_comparable_across_extensions(self):
        source = evidence("FPS stutter and frame drops make the game frustrating.")
        gacha = annotate_evidence(source, game("gacha"))
        mmo = annotate_evidence(source, game("mmorpg"))
        self.assertEqual(gacha.primary_topic, "performance")
        self.assertEqual(mmo.primary_topic, "performance")

    def test_other_unclassified_is_never_priority_eligible(self):
        annotation = annotate_evidence(evidence("I played for two hours yesterday."), game("action"))
        self.assertEqual(annotation.primary_topic, "other_unclassified")
        self.assertTrue(annotation.requires_human_review)
        self.assertFalse(priority_eligible_topic(annotation.primary_topic))

    def test_generic_praise_remains_unclassified(self):
        for index, text in enumerate(["好玩", "GOOD", "很牛逼"]):
            with self.subTest(text=text):
                annotation = annotate_evidence(
                    evidence(text, suffix=f"generic-{index}", recommended=True, language="zh-CN"),
                    game("action"),
                )
                self.assertEqual(annotation.primary_topic, "other_unclassified")

    def test_fair_play_integrity_covers_cheating_anticheat_and_bots(self):
        for index, text in enumerate(["外挂太多", "反作弊误封正常玩家", "人机太多了"]):
            with self.subTest(text=text):
                annotation = annotate_evidence(
                    evidence(text, suffix=f"integrity-{index}", language="zh-CN"),
                    game("shooter"),
                )
                self.assertEqual(annotation.primary_topic, "fair_play_integrity")

    def test_audited_rule_gaps_classify_existing_taxonomy_topics(self):
        cases = [
            ("It's not bad; stay away from using money for the gachas.", "gacha"),
            ("It freezes before the download finishes.", "bugs_stability"),
            ("这个游戏全是职业选手", "difficulty"),
            ("垃圾箱子，圈钱第一名", "monetisation"),
        ]
        for index, (text, expected) in enumerate(cases):
            with self.subTest(text=text):
                annotation = annotate_evidence(
                    evidence(text, suffix=f"gap-{index}"),
                    game("action"),
                )
                self.assertEqual(annotation.primary_topic, expected)

    def test_payment_withdrawal_remains_expressed_intent(self):
        annotation = annotate_evidence(
            evidence("号太黑，抽不出来好东西，再也不充了", language="zh-CN"),
            game("action"),
        )
        self.assertEqual(annotation.primary_topic, "gacha")
        self.assertIn("payment_withdrawal", annotation.behaviour_signals)
        self.assertEqual(
            annotation.method["behaviour_semantics"],
            "expressed_intent_not_observed_behaviour",
        )

    def test_story_pain_point_has_explicitly_inferred_need(self):
        annotation = annotate_evidence(
            evidence("剧情很无聊。", language="zh-CN"),
            game("adventure"),
        )
        self.assertEqual(annotation.primary_topic, "story")
        self.assertTrue(annotation.pain_points)
        self.assertEqual(
            annotation.underlying_needs,
            ["coherent and engaging narrative delivery"],
        )

    def test_behaviour_requires_explicit_cue_and_is_expressed_intent(self):
        source = evidence("新版本之后手机越来越烫，最近都不太想上线了。", language="zh-CN")
        annotation = annotate_evidence(source, game("gacha"))
        self.assertEqual(annotation.primary_topic, "performance")
        self.assertIn("churn_risk", annotation.behaviour_signals)
        self.assertIn("device overheating after update", annotation.pain_points)
        self.assertEqual(annotation.explicit_feature_requests, [])
        self.assertEqual(
            annotation.method["behaviour_semantics"],
            "expressed_intent_not_observed_behaviour",
        )

    def test_feature_request_requires_explicit_request_language(self):
        requested = annotate_evidence(
            evidence("Please add full controller remapping."),
            game("action"),
        )
        complaint = annotate_evidence(
            evidence("Controller input lag is terrible."),
            game("action"),
        )
        self.assertEqual(requested.explicit_feature_requests, ["Please add full controller remapping."])
        self.assertIn("feature_request", requested.behaviour_signals)
        self.assertEqual(complaint.explicit_feature_requests, [])

    def test_hope_expression_is_not_an_explicit_feature_request(self):
        hopeful = annotate_evidence(
            evidence("这个系统一直在更新，我依然抱有希望。", language="zh-CN"),
            game("simulation"),
        )
        requested = annotate_evidence(
            evidence("我希望可以增加一键跳过。", language="zh-CN"),
            game("simulation"),
        )
        self.assertEqual(hopeful.explicit_feature_requests, [])
        self.assertNotIn("feature_request", hopeful.behaviour_signals)
        self.assertEqual(requested.explicit_feature_requests, ["我希望可以增加一键跳过。"])

    def test_player_advice_is_not_a_product_feature_request(self):
        annotation = annotate_evidence(
            evidence("建议还是在官网下载安装，请去官网下载哦。", language="zh-CN"),
            game("simulation"),
        )
        self.assertEqual(annotation.explicit_feature_requests, [])
        self.assertNotIn("feature_request", annotation.behaviour_signals)

    def test_mixed_neutral_and_unknown_sentiment_are_supported(self):
        mixed = annotate_evidence(evidence("Combat is great but the controls are terrible."), game("action"))
        neutral = annotate_evidence(evidence("The tutorial is average."), game("action"))
        unknown = annotate_evidence(evidence("The tutorial has five chapters."), game("action"))
        self.assertEqual(mixed.sentiment_label.value, "mixed")
        self.assertEqual(neutral.sentiment_label.value, "neutral")
        self.assertEqual(unknown.sentiment_label.value, "unknown")

    def test_existing_sample_reannotates_without_losing_evidence_links(self):
        frame = pd.read_csv(ROOT / "data/processed/voice.csv")
        items = [
            normalized_voice_row_to_evidence(
                row,
                game_id="game_annotation",
                run_id="run_annotation",
            )
            for row in frame.to_dict(orient="records")
        ]
        annotations = annotate_corpus(items, game("gacha", "mmorpg"))
        self.assertEqual(len(annotations), 327)
        self.assertEqual(
            {value.evidence_id for value in annotations},
            {value.evidence_id for value in items},
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "annotations.jsonl"
            self.assertEqual(write_annotations_jsonl(annotations, output), 327)
            self.assertEqual(len(output.read_text(encoding="utf-8").splitlines()), 327)


if __name__ == "__main__":
    unittest.main()
