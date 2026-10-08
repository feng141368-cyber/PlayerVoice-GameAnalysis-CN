from __future__ import annotations

import unittest
from pathlib import Path

from gamepulse.modes import ModeRequest, load_core_snapshot, route_mode
from gamepulse.modes.creator import CreatorBrief, CreatorControversy, ControversyPosition


ROOT = Path(__file__).resolve().parents[1]


class CreatorModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.infinity = load_core_snapshot(ROOT / "examples/e2e/infinity-nikki")
        cls.pubg = load_core_snapshot(ROOT / "examples/e2e/pubg-battlegrounds")

    def _response(self, snapshot, request_id="creator"):
        return route_mode(
            ModeRequest(
                request_id=request_id,
                mode="creator",
                games=[snapshot.game.game_id],
                research_intents=["praise", "complaints", "controversy"],
            ),
            [snapshot],
        )

    def test_creator_brief_contains_required_sections(self):
        response = self._response(self.infinity)
        brief = CreatorBrief.model_validate(response.payload)
        self.assertTrue(brief.game_current_context)
        self.assertTrue(brief.praise)
        self.assertTrue(brief.complaints)
        self.assertTrue(brief.questions_worth_investigating)
        self.assertTrue(brief.research_gaps)
        self.assertTrue(brief.platform_language_differences)
        self.assertTrue(brief.representative_evidence_ids)

    def test_controvsery_requires_two_distinguishable_positions(self):
        brief = CreatorBrief.model_validate(self._response(self.infinity).payload)
        story = next(value for value in brief.controversies if value.topic == "story")
        self.assertGreaterEqual(len(story.side_a.evidence_ids), 2)
        self.assertGreaterEqual(len(story.side_b.evidence_ids), 2)
        self.assertFalse(set(story.side_a.evidence_ids).intersection(story.side_b.evidence_ids))
        self.assertTrue(story.side_a.representative_statements)
        self.assertTrue(story.side_b.representative_statements)

    def test_weak_opposition_cannot_validate_as_controversy(self):
        with self.assertRaisesRegex(ValueError, "at least 2 items"):
            CreatorControversy(
                topic="performance",
                question="Is performance good?",
                side_a=ControversyPosition(
                    label="positive",
                    summary="one positive",
                    evidence_ids=["ev_one"],
                    representative_statements=[{"evidence_id": "ev_one", "statement": "good"}],
                ),
                side_b=ControversyPosition(
                    label="negative",
                    summary="one negative",
                    evidence_ids=["ev_two", "ev_three"],
                    representative_statements=[{"evidence_id": "ev_two", "statement": "bad"}],
                ),
                insight_ids=["insight_one"],
                confidence=0.5,
                evidence_coverage={},
                research_gap="more evidence needed",
            )

    def test_no_controversy_is_explicit_instead_of_fabricated(self):
        brief = CreatorBrief.model_validate(self._response(self.pubg, "creator_pubg").payload)
        self.assertEqual(brief.controversies, [])
        self.assertEqual(brief.controversy_status, "No well-supported controversy detected.")

    def test_questions_are_labelled_not_established_findings(self):
        brief = CreatorBrief.model_validate(self._response(self.infinity).payload)
        for question in brief.questions_worth_investigating:
            self.assertEqual(question.classification, "research_question")
            self.assertTrue(question.not_an_established_finding)
            self.assertTrue(question.evidence_ids)

    def test_platform_language_difference_requires_comparable_breadth(self):
        brief = CreatorBrief.model_validate(self._response(self.infinity).payload)
        self.assertEqual(brief.platform_language_differences[0].layer, "insufficient")
        self.assertIn("Insufficient comparable", brief.platform_language_differences[0].statement)

    def test_creator_response_resolves_all_evidence(self):
        response = self._response(self.infinity)
        referenced = {value.evidence_id for value in response.evidence_references}
        brief = CreatorBrief.model_validate(response.payload)
        linked = set(brief.representative_evidence_ids)
        for controversy in brief.controversies:
            linked.update(controversy.side_a.evidence_ids)
            linked.update(controversy.side_b.evidence_ids)
        for question in brief.questions_worth_investigating:
            linked.update(question.evidence_ids)
        self.assertTrue(linked.issubset(referenced))


if __name__ == "__main__":
    unittest.main()
