from __future__ import annotations

import unittest
from datetime import datetime, timezone

from gamepulse.aliases import (
    AliasDiscoveryResult,
    AliasObservation,
    SteamAliasObservationProvider,
    discover_aliases,
)
from gamepulse.models import GameEntity


NOW = datetime(2026, 9, 29, tzinfo=timezone.utc)


def resolved_game() -> GameEntity:
    return GameEntity(
        game_id="game_wikidata_q105735622",
        canonical_title="Tower of Fantasy",
        original_title="幻塔",
        localized_titles={"en": "Tower of Fantasy", "zh-CN": "幻塔"},
        external_ids={"wikidata_id": "Q105735622", "steam_app_id": "2064650"},
        developers=["Hotta Studio"],
        publishers=["Perfect World"],
        resolution_status="resolved",
        resolution_confidence=0.98,
        resolution_evidence_ids=["ev_resolver_tower"],
        resolved_at=NOW,
        platforms=["Windows", "iOS", "Android"],
    )


class AliasTests(unittest.TestCase):
    def test_official_chinese_and_english_titles_are_standalone_safe(self):
        result = discover_aliases(resolved_game())
        by_text = {alias.text: alias for alias in result.aliases}
        for text in ["Tower of Fantasy", "幻塔"]:
            self.assertEqual(by_text[text].validation_status.value, "validated")
            self.assertTrue(by_text[text].standalone_search_safe)
            self.assertTrue(by_text[text].source_evidence_ids)

    def test_high_ambiguity_abbreviation_is_scoped_only(self):
        observation = AliasObservation(
            text="TOF", language="en", proposed_type="abbreviation",
            source_evidence_ids=["ev_forum_1"], source_platforms=["reddit"],
            evidence_basis="community_self_reference", confidence=0.9,
            ambiguity="high", ambiguity_notes="also means time of flight",
        )
        result = discover_aliases(resolved_game(), [observation])
        alias = next(alias for alias in result.aliases if alias.text == "TOF")
        self.assertEqual(alias.validation_status.value, "scoped_only")
        self.assertTrue(alias.search_enabled)
        self.assertFalse(alias.standalone_search_safe)
        self.assertNotIn(alias, result.query_ready_aliases())
        self.assertIn(alias, result.query_ready_aliases(include_scoped=True))

    def test_cooccurring_character_name_stays_pending(self):
        observation = AliasObservation(
            text="Shirli", language="en", proposed_type="community_nickname",
            source_evidence_ids=["ev_post_1", "ev_post_2"], source_platforms=["reddit"],
            evidence_basis="co_occurrence_only", confidence=0.95,
        )
        result = discover_aliases(resolved_game(), [observation])
        alias = next(alias for alias in result.aliases if alias.text == "Shirli")
        self.assertEqual(alias.validation_status.value, "pending")
        self.assertFalse(alias.search_enabled)

    def test_normalization_duplicates_merge_all_provenance(self):
        observations = [
            AliasObservation(
                text="T.O.F.", language="en", proposed_type="abbreviation",
                source_evidence_ids=["ev_1"], source_platforms=["reddit"],
                evidence_basis="editorial_reference", confidence=0.8, ambiguity="medium",
                source_references=["https://example.test/one"],
            ),
            AliasObservation(
                text="tof", language="en", proposed_type="abbreviation",
                source_evidence_ids=["ev_2"], source_platforms=["bilibili"],
                evidence_basis="repeated_independent_usage", confidence=0.9, ambiguity="medium",
                source_references=["https://example.test/two"],
            ),
        ]
        result = discover_aliases(resolved_game(), observations)
        merged = [alias for alias in result.aliases if alias.normalized_text == "tof"]
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].source_evidence_ids, ["ev_1", "ev_2"])
        self.assertEqual(merged[0].source_platforms, ["bilibili", "reddit"])
        review = next(item for item in result.review_items if item.alias_id == merged[0].alias_id)
        self.assertEqual(len(review.source_references), 2)

    def test_platform_scoped_nickname_retains_platform(self):
        observation = AliasObservation(
            text="Hotta dress-up", language="en", proposed_type="community_nickname",
            source_evidence_ids=["ev_r1", "ev_r2"], source_platforms=["reddit"],
            evidence_basis="repeated_independent_usage", confidence=0.9,
            platform_scope_required=True,
        )
        result = discover_aliases(resolved_game(), [observation])
        alias = next(alias for alias in result.aliases if alias.text == "Hotta dress-up")
        self.assertEqual(alias.source_platforms, ["reddit"])
        self.assertEqual(alias.validation_status.value, "scoped_only")

    def test_misspelling_and_nickname_rules_are_covered(self):
        observations = [
            AliasObservation(
                text="Tower of Fantasty", language="en", proposed_type="common_misspelling",
                source_evidence_ids=["ev_misspelling"], source_platforms=["youtube"],
                evidence_basis="editorial_reference", confidence=0.9,
            ),
            AliasObservation(
                text="Aida Online", language="en", proposed_type="community_nickname",
                source_evidence_ids=["ev_n1", "ev_n2"], source_platforms=["reddit", "youtube"],
                evidence_basis="repeated_independent_usage", confidence=0.9,
            ),
        ]
        result = discover_aliases(resolved_game(), observations)
        by_text = {alias.text: alias for alias in result.aliases}
        self.assertEqual(by_text["Tower of Fantasty"].validation_status.value, "validated")
        self.assertEqual(by_text["Aida Online"].validation_status.value, "validated")

    def test_alias_provenance_survives_serialization(self):
        observation = AliasObservation(
            text="TOF", language="en", proposed_type="abbreviation",
            source_evidence_ids=["ev_alias_source"], source_platforms=["steam"],
            evidence_basis="editorial_reference", confidence=0.8, ambiguity="low",
            source_references=["https://example.test/alias-source"],
        )
        result = discover_aliases(resolved_game(), [observation])
        rebuilt = AliasDiscoveryResult.from_dict(result.to_dict())
        alias = next(alias for alias in rebuilt.aliases if alias.text == "TOF")
        self.assertEqual(alias.source_evidence_ids, ["ev_alias_source"])
        self.assertEqual(alias.source_platforms, ["steam"])
        self.assertEqual(rebuilt.observations[0].source_references, ["https://example.test/alias-source"])

    def test_steam_search_validates_derived_abbreviation_with_real_reference_shape(self):
        cs2 = resolved_game().model_copy(
            update={
                "game_id": "game_steam_730",
                "canonical_title": "Counter-Strike 2",
                "original_title": "Counter-Strike 2",
                "localized_titles": {"en": "Counter-Strike 2"},
                "external_ids": {"steam_app_id": "730"},
            }
        )

        def requester(url, **kwargs):
            self.assertEqual(kwargs["params"]["term"], "CS2")
            return {
                "items": [
                    {"id": 730, "name": "Counter-Strike 2"},
                    {"id": 666220, "name": "CS2D"},
                ]
            }

        observations = SteamAliasObservationProvider(requester=requester).discover(cs2)
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].text, "CS2")
        self.assertEqual(observations[0].ambiguity.value, "high")
        self.assertTrue(observations[0].source_evidence_ids[0].startswith("ev_alias_"))
        self.assertIn("store.steampowered.com/search", observations[0].source_references[0])
        self.assertIn("Counter-Strike 2", observations[0].source_excerpts[0])
        self.assertIn("CS2D", observations[0].source_excerpts[0])
        aliases = discover_aliases(cs2, observations)
        alias = next(item for item in aliases.aliases if item.text == "CS2")
        self.assertEqual(alias.validation_status.value, "scoped_only")
        self.assertFalse(alias.standalone_search_safe)


if __name__ == "__main__":
    unittest.main()
