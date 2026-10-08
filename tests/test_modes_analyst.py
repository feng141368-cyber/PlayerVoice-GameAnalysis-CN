from __future__ import annotations

import json
import unittest
from pathlib import Path

from gamepulse.insights import DECISION_SUPPORT_DISCLAIMER
from gamepulse.modes import ModeRequest, load_core_snapshot, route_mode
from gamepulse.modes.analyst import AnalystReport


ROOT = Path(__file__).resolve().parents[1]


class AnalystModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.infinity = load_core_snapshot(ROOT / "examples/e2e/infinity-nikki")
        cls.cs2 = load_core_snapshot(ROOT / "examples/e2e/counter-strike-2")

    def _response(self, snapshot, request_id="analyst"):
        return route_mode(
            ModeRequest(
                request_id=request_id,
                mode="analyst",
                games=[snapshot.game.game_id],
                research_intents=["pain_points", "retention", "opportunities"],
            ),
            [snapshot],
        )

    def test_chain_distinguishes_observed_inferred_expressed_and_hypothesis(self):
        report = AnalystReport.model_validate(self._response(self.infinity).payload)
        finding = next(
            value
            for value in report.findings
            if value.evidence.evidence_ids == ["ev_2a50adf719624154de4b"]
        )
        self.assertEqual(finding.evidence.status, "observed")
        self.assertEqual(finding.topic.status, "inferred")
        self.assertTrue(finding.pain_points)
        self.assertTrue(all(value.status == "inferred" for value in finding.pain_points))
        self.assertTrue(finding.underlying_needs)
        self.assertTrue(all(value.status == "expressed_intent" for value in finding.expressed_behaviour_signals))
        self.assertTrue(all(value.status == "hypothesis" for value in finding.possible_business_relevance))

    def test_churn_wording_never_claims_observed_churn_or_causality(self):
        response = self._response(self.infinity)
        rendered = json.dumps(response.to_dict(), ensure_ascii=False).casefold()
        self.assertIn("expressed_churn_intent", rendered)
        self.assertNotIn("player churned", rendered)
        self.assertNotIn("causes churn", rendered)
        self.assertIn("does not establish behavioural impact or causality", rendered)

    def test_explicit_request_and_inferred_opportunity_are_separate(self):
        report = AnalystReport.model_validate(self._response(self.infinity).payload)
        finding = next(
            value
            for value in report.findings
            if value.explicit_feature_requests and value.underlying_needs
        )
        self.assertTrue(all(value.status == "observed" for value in finding.explicit_feature_requests))
        statuses = {value.status for value in finding.product_opportunities}
        self.assertIn("observed", statuses)
        self.assertIn("inferred", statuses)

    def test_priority_is_decision_support_not_causal_estimate(self):
        report = AnalystReport.model_validate(self._response(self.infinity).payload)
        priorities = [value.priority for value in report.findings if value.priority]
        self.assertTrue(priorities)
        self.assertTrue(all(value["disclaimer"] == DECISION_SUPPORT_DISCLAIMER for value in priorities))
        self.assertEqual(report.priority_disclaimer, DECISION_SUPPORT_DISCLAIMER)

    def test_public_scope_and_no_observed_behaviour_data(self):
        report = AnalystReport.model_validate(self._response(self.infinity).payload)
        self.assertEqual(report.data_scope, "public_corpus_only")
        self.assertFalse(report.observed_behaviour_data_available)
        self.assertTrue(any("authorised observed-behaviour" in value for value in report.research_gaps))

    def test_insufficient_actionable_data_returns_research_gap(self):
        report = AnalystReport.model_validate(self._response(self.cs2, "analyst_cs2").payload)
        self.assertEqual(report.findings, [])
        self.assertIn("No actionable evidence chain", report.research_gaps[0])

    def test_analyst_evidence_traceback_resolves(self):
        response = self._response(self.infinity)
        report = AnalystReport.model_validate(response.payload)
        referenced = {value.evidence_id for value in response.evidence_references}
        linked = {
            evidence_id
            for finding in report.findings
            for stage in [
                finding.evidence,
                finding.topic,
                *finding.pain_points,
                *finding.underlying_needs,
                *finding.expressed_behaviour_signals,
                *finding.possible_business_relevance,
                *finding.product_opportunities,
                *finding.explicit_feature_requests,
            ]
            for evidence_id in stage.evidence_ids
        }
        self.assertEqual(linked, referenced)


if __name__ == "__main__":
    unittest.main()
