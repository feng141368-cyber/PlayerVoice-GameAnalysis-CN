from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from gamepulse.facts import (
    JsonFactStore,
    SteamStoreFactAdapter,
    StructuredOfficialFactAdapter,
    build_can_i_run_it,
    collect_fact_layer,
    reconcile_facts,
)
from gamepulse.models import GameEntity, QueryPlan


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/facts"
NOW = datetime(2026, 9, 29, tzinfo=timezone.utc)


def game() -> GameEntity:
    return GameEntity(
        game_id="game_wikidata_q105735622", canonical_title="Tower of Fantasy", original_title="幻塔",
        localized_titles={"en": "Tower of Fantasy", "zh-CN": "幻塔"},
        external_ids={"wikidata_id": "Q105735622", "steam_app_id": "2064650"},
        developers=["Hotta Studio"], publishers=["Perfect World"], resolution_status="resolved",
        resolution_confidence=0.98, resolution_evidence_ids=["ev_resolver_tower"], resolved_at=NOW,
        platforms=["Windows", "PlayStation 5", "iOS", "Android"],
    )


def steam_bundle():
    payload = json.loads((FIXTURES / "steam_appdetails_2064650.json").read_text(encoding="utf-8"))
    return SteamStoreFactAdapter.from_payload(
        game(), payload["2064650"]["data"], app_id="2064650", run_id="run_facts",
        territory="US", retrieved_at=NOW,
    )


def official_bundle(payload_override=None):
    payload = json.loads((FIXTURES / "official_tower_of_fantasy.json").read_text(encoding="utf-8"))
    if payload_override:
        payload_override(payload)
    return StructuredOfficialFactAdapter(payload).collect(game(), run_id="run_facts")


class FactLayerTests(unittest.TestCase):
    def test_store_and_official_fixtures_produce_atomic_linked_facts(self):
        bundle = reconcile_facts([steam_bundle(), official_bundle()])
        evidence_ids = {item.evidence_id for item in bundle.evidence}
        self.assertGreater(len(bundle.facts), 10)
        self.assertTrue(all(fact.source_evidence_id in evidence_ids for fact in bundle.facts))
        self.assertTrue(all(fact.retrieved_at.tzinfo is not None for fact in bundle.facts))
        self.assertEqual(
            {fact.source_authority.value for fact in bundle.facts}, {"official", "platform_store"},
        )

    def test_minimum_and_recommended_requirements_remain_distinct(self):
        bundle = steam_bundle()
        minimum = bundle.facts_by_type("minimum_requirements")
        recommended = bundle.facts_by_type("recommended_requirements")
        self.assertEqual(len(minimum), 1)
        self.assertEqual(len(recommended), 1)
        self.assertNotEqual(minimum[0].value, recommended[0].value)
        storage = bundle.facts_by_type("storage_requirement")
        self.assertEqual({fact.value["tier"] for fact in storage}, {"minimum", "recommended"})

    def test_missing_cross_save_does_not_create_affirmative_fact(self):
        bundle = reconcile_facts([steam_bundle(), official_bundle()])
        self.assertEqual(bundle.facts_by_type("cross_save"), [])
        self.assertEqual(bundle.facts_by_type("cross_play")[0].value, True)

    def test_conflicting_sources_remain_visible(self):
        first = official_bundle()

        def change_version(payload):
            payload["facts"]["current_version"] = "6.3"
            payload["source_content_id"] = "official-support-page"
            payload["source_url"] = "https://example.test/official/support"

        second = official_bundle(change_version)
        combined = reconcile_facts([first, second])
        versions = combined.facts_by_type("current_version")
        self.assertEqual({fact.value for fact in versions}, {"6.2", "6.3"})
        self.assertTrue(all(fact.verification_status.value == "conflicting" for fact in versions))

    def test_platform_and_territory_scope_survive(self):
        combined = reconcile_facts([steam_bundle(), official_bundle()])
        windows = [fact for fact in combined.facts if fact.platform == "Windows"]
        playstation = [fact for fact in combined.facts if fact.platform == "PlayStation 5"]
        self.assertTrue(windows)
        self.assertTrue(playstation)
        self.assertEqual({fact.territory for fact in windows}, {"US", "global"})

    def test_fact_store_is_separate_and_queryable_without_ugc(self):
        combined = reconcile_facts([steam_bundle(), official_bundle()])
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFactStore(Path(directory))
            store.save(combined)
            facts = store.query(game().game_id, fact_types={"developer"})
            self.assertTrue(facts)
            self.assertFalse((Path(directory) / "voice.csv").exists())
            self.assertTrue(store.evidence(game().game_id))

    def test_can_i_run_it_bundle_contains_only_official_fact_layer(self):
        combined = reconcile_facts([steam_bundle(), official_bundle()])
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFactStore(Path(directory))
            store.save(combined)
            result = build_can_i_run_it(store, game().game_id, platform="Windows")
        self.assertEqual(result.layer, "official_fact")
        self.assertTrue(result.minimum_requirements)
        self.assertTrue(result.recommended_requirements)
        self.assertTrue(result.storage_requirements)
        self.assertTrue(result.evidence_ids)
        self.assertNotIn("player_report", {fact.fact_type for fact in result.minimum_requirements})

    def test_live_adapter_contract_uses_steam_app_identity_and_query_link(self):
        payload = json.loads((FIXTURES / "steam_appdetails_2064650.json").read_text(encoding="utf-8"))
        calls = []

        def requester(url, **kwargs):
            calls.append((url, kwargs))
            return payload

        adapter = SteamStoreFactAdapter(requester=requester)
        query = QueryPlan(
            query_id="query_steam", run_id="run_facts", game_id=game().game_id, source="steam", language="en",
            intent="performance", query_text="steam_app:2064650 intent:performance",
            alias_ids=["alias_title"], disambiguators=[], expected_evidence_kind="review", generated_at=NOW,
        )
        bundle = collect_fact_layer(game(), [adapter], run_id="run_facts", query_plans=[query])
        self.assertEqual(calls[0][1]["params"]["appids"], "2064650")
        self.assertEqual(bundle.evidence[0].query_id, "query_steam")


if __name__ == "__main__":
    unittest.main()
