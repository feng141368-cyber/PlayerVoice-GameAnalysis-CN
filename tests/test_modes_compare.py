from __future__ import annotations

import json
import unittest
from pathlib import Path

from gamepulse.modes import ModeRequest, load_core_snapshot, route_mode
from gamepulse.modes.compare import CompareReport, build_compare_report


ROOT = Path(__file__).resolve().parents[1]
PREFERENCE_TEXT = (
    "我每天大概只能玩一个小时。"
    "我喜欢探索、剧情和角色塑造。"
    "我不喜欢重 PvP，也不喜欢每天必须上线做很多任务。"
    "比较在乎画面和音乐。"
)


class CompareModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshots = [
            load_core_snapshot(ROOT / "examples/e2e/infinity-nikki"),
            load_core_snapshot(ROOT / "examples/e2e/pubg-battlegrounds"),
            load_core_snapshot(ROOT / "examples/e2e/counter-strike-2"),
        ]

    def _response(self, preferences=None):
        return route_mode(
            ModeRequest(
                request_id="compare_three_games",
                mode="compare",
                games=[value.game.game_id for value in self.snapshots],
                preferences=preferences,
            ),
            self.snapshots,
        )

    def test_three_game_comparison_reuses_one_taxonomy(self):
        report = CompareReport.model_validate(self._response().payload)
        self.assertEqual(len(report.game_ids), 3)
        self.assertEqual(report.taxonomy_version, "1.1.0")
        self.assertTrue(report.dimensions)
        self.assertTrue(all(len(value.cells) == 3 for value in report.dimensions))

    def test_raw_counts_normalized_share_and_coverage_are_visible(self):
        report = CompareReport.model_validate(self._response().payload)
        performance = next(value for value in report.dimensions if value.dimension == "performance")
        for cell in performance.cells:
            self.assertGreaterEqual(cell.evidence_count, 0)
            self.assertGreaterEqual(cell.corpus_share_percent, 0)
            self.assertIsInstance(cell.source_distribution, dict)
            self.assertIsInstance(cell.language_distribution, dict)
            self.assertIn(cell.confidence, {"insufficient", "low", "medium", "higher"})
        self.assertTrue(all(value.relevant_corpus_size > 0 for value in report.coverage))

    def test_missing_dimension_blocks_comparison_instead_of_scoring_average(self):
        report = CompareReport.model_validate(self._response().payload)
        exploration = next(value for value in report.dimensions if value.dimension == "exploration")
        self.assertEqual(exploration.status, "insufficient_evidence")
        self.assertTrue(any(value.evidence_count < 3 for value in exploration.cells))
        self.assertIn("no reliable cross-game difference", exploration.reason)

    def test_fact_layer_values_and_missing_facts_are_explicit(self):
        report = CompareReport.model_validate(self._response().payload)
        platforms = next(value for value in report.fact_dimensions if value.fact_type == "platform_support")
        self.assertEqual(platforms.status, "comparable")
        self.assertTrue(all(value.fact_ids and value.evidence_ids for value in platforms.cells))
        minimum = next(value for value in report.fact_dimensions if value.fact_type == "minimum_requirements")
        self.assertTrue(all(value.status == "available" for value in minimum.cells))

    def test_no_winner_or_universal_numeric_score_is_emitted(self):
        response = self._response()
        report = CompareReport.model_validate(response.payload)
        self.assertTrue(report.no_winner_score)
        rendered = json.dumps(response.to_dict(), ensure_ascii=False).casefold()
        self.assertNotIn('"winner"', rendered)
        self.assertNotIn("recommendation score", rendered)

    def test_optional_preference_profile_produces_per_game_dimensions(self):
        report = CompareReport.model_validate(self._response(PREFERENCE_TEXT).payload)
        self.assertIsNotNone(report.preference_profile)
        self.assertEqual(set(report.preference_fit), set(report.game_ids))
        for game_id in report.game_ids:
            self.assertTrue(report.preference_fit[game_id])
            self.assertTrue(
                all(value.assessment in {"likely_match", "possible_friction", "uncertain"}
                    for value in report.preference_fit[game_id])
            )

    def test_all_linked_evidence_resolves_to_original_source(self):
        response = self._response()
        report = CompareReport.model_validate(response.payload)
        linked = {
            evidence_id
            for dimension in report.dimensions
            for cell in dimension.cells
            for evidence_id in cell.evidence_ids
        }
        linked.update(
            evidence_id
            for dimension in report.fact_dimensions
            for cell in dimension.cells
            for evidence_id in cell.evidence_ids
        )
        referenced = {value.evidence_id for value in response.evidence_references}
        self.assertEqual(linked, referenced)
        self.assertTrue(
            all(value.source_url or value.source_reference for value in response.evidence_references)
        )
        self.assertTrue(all(len(value) < 400 for value in response.limitations))

    def test_duplicate_game_and_taxonomy_mismatch_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "distinct game"):
            build_compare_report([self.snapshots[0], self.snapshots[0]])
        mismatched = self.snapshots[1].model_copy(deep=True)
        mismatched.annotations[0].taxonomy_version = "999.0.0"
        with self.assertRaisesRegex(ValueError, "shared taxonomy"):
            build_compare_report([self.snapshots[0], mismatched])


if __name__ == "__main__":
    unittest.main()
