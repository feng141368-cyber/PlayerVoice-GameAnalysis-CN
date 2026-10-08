from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gamepulse.aliases import AliasObservation
from gamepulse.facts import StructuredOfficialFactAdapter
from gamepulse.foundation import FoundationResult, run_foundation_slice
from gamepulse.query_builder import QueryBuilderSettings
from gamepulse.resolver import FixtureResolverProvider, ResolverCache


ROOT = Path(__file__).resolve().parents[1]
RESOLVER_FIXTURE = ROOT / "tests/fixtures/resolver/catalog.json"
FACT_FIXTURE = ROOT / "tests/fixtures/facts/official_tower_of_fantasy.json"


class StaticAliasProvider:
    name = "static_test_provider"

    def discover(self, game):
        return [
            AliasObservation(
                text="TOF", language="en", proposed_type="abbreviation",
                source_evidence_ids=["ev_alias_fixture"], source_platforms=["steam"],
                evidence_basis="platform_search_match", confidence=0.9, ambiguity="high",
                source_references=["https://example.test/search?q=TOF"],
            )
        ]


class FailingAliasProvider:
    name = "failing_alias"

    def discover(self, game):
        raise TimeoutError("fixture timeout")


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache = ResolverCache(Path(self.temp_dir.name))
        self.resolver = FixtureResolverProvider(RESOLVER_FIXTURE)
        payload = json.loads(FACT_FIXTURE.read_text(encoding="utf-8"))
        self.fact_adapter = StructuredOfficialFactAdapter(payload)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_complete_issue_1_to_5_slice_runs_without_ugc(self):
        result = run_foundation_slice(
            "Tower of Fantasy",
            locale="en",
            run_id="run_foundation_test",
            resolver_providers=[self.resolver],
            resolver_cache=self.cache,
            alias_providers=[StaticAliasProvider()],
            query_settings=QueryBuilderSettings(
                languages=["en", "zh-CN"], sources=["official", "steam", "reddit", "bilibili"],
                intents=["general", "performance", "controls", "patch"], max_per_source_intent=2,
            ),
            fact_adapters=[self.fact_adapter],
        )
        self.assertEqual(result.resolution.status.value, "resolved")
        self.assertIsNotNone(result.aliases)
        self.assertTrue(result.query_plans)
        self.assertTrue(result.fact_bundle.facts)
        self.assertFalse(any("voice.csv" in warning for warning in result.stage_warnings))
        rebuilt = FoundationResult.from_dict(result.to_dict())
        self.assertEqual(rebuilt.resolution.game.game_id, result.resolution.game.game_id)

    def test_unresolved_input_stops_without_fabricating_downstream_data(self):
        result = run_foundation_slice(
            "Definitely Not A Real Game", locale="en", run_id="run_unknown",
            resolver_providers=[self.resolver], resolver_cache=self.cache,
            alias_providers=[], fact_adapters=[self.fact_adapter],
        )
        self.assertEqual(result.resolution.status.value, "unresolved")
        self.assertIsNone(result.aliases)
        self.assertEqual(result.query_plans, [])
        self.assertIsNone(result.fact_bundle)

    def test_alias_provider_failure_falls_back_to_official_titles(self):
        result = run_foundation_slice(
            "Tower of Fantasy", locale="en", run_id="run_alias_failure",
            resolver_providers=[self.resolver], resolver_cache=self.cache,
            alias_providers=[FailingAliasProvider()], fact_adapters=[self.fact_adapter],
        )
        self.assertTrue(result.aliases.standalone_aliases())
        self.assertIn("alias provider failing_alias unavailable", result.stage_warnings[0])


if __name__ == "__main__":
    unittest.main()
