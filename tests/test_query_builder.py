from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from gamepulse.aliases import AliasDiscoveryResult, AliasObservation, discover_aliases
from gamepulse.models import GameAlias, GameEntity
from gamepulse.query_builder import QueryBuilderSettings, build_query_plans, default_query_languages
from gamepulse.resolver import ResolutionResult
from scripts.gamepulse import command_plan


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 29, tzinfo=timezone.utc)


def game() -> GameEntity:
    return GameEntity(
        game_id="game_wikidata_q105735622", canonical_title="Tower of Fantasy", original_title="幻塔",
        localized_titles={"en": "Tower of Fantasy", "zh-CN": "幻塔"},
        external_ids={"wikidata_id": "Q105735622", "steam_app_id": "2064650"},
        developers=["Hotta Studio"], publishers=["Perfect World"], resolution_status="resolved",
        resolution_confidence=0.98, resolution_evidence_ids=["ev_resolver_tower"], resolved_at=NOW,
        platforms=["Windows", "iOS", "Android"],
    )


def alias_result() -> AliasDiscoveryResult:
    observations = [
        AliasObservation(
            text="TOF", language="en", proposed_type="abbreviation", source_evidence_ids=["ev_tof"],
            source_platforms=["reddit"], evidence_basis="editorial_reference", confidence=0.9,
            ambiguity="high", ambiguity_notes="time of flight",
        ),
        AliasObservation(
            text="Shirli", language="en", proposed_type="community_nickname", source_evidence_ids=["ev_character"],
            source_platforms=["reddit"], evidence_basis="co_occurrence_only", confidence=0.95,
        ),
    ]
    return discover_aliases(game(), observations)


class QueryBuilderTests(unittest.TestCase):
    def build(self, **overrides):
        settings = QueryBuilderSettings(
            languages=overrides.get("languages", ["zh-CN", "en"]),
            sources=overrides.get("sources", ["official", "steam", "reddit", "bilibili"]),
            intents=overrides.get("intents", ["general"]),
            max_per_source_intent=overrides.get("cap", 3),
        )
        return build_query_plans(game(), alias_result(), run_id="run_test", settings=settings, generated_at=NOW)

    def test_bilingual_entity_produces_separate_language_plans(self):
        plans = self.build(sources=["official"], intents=["general"])
        self.assertEqual({plan.language for plan in plans}, {"zh-CN", "en"})
        self.assertTrue(any("幻塔" in plan.query_text for plan in plans))
        self.assertTrue(any("Tower of Fantasy" in plan.query_text for plan in plans))

    def test_default_languages_collapse_chinese_locale_variants(self):
        entity = game().model_copy(
            update={"localized_titles": {"zh": "幻塔", "zh-hans": "幻塔", "zh-CN": "幻塔", "en": "Tower of Fantasy"}}
        )
        self.assertEqual(default_query_languages(entity), ["zh-CN", "en"])

    def test_identical_localized_title_remains_usable_for_each_language(self):
        entity = game().model_copy(
            update={"canonical_title": "PUBG: BATTLEGROUNDS", "localized_titles": {"en": "PUBG: BATTLEGROUNDS", "zh-CN": "PUBG: BATTLEGROUNDS"}}
        )
        aliases = discover_aliases(entity)
        plans = build_query_plans(
            entity,
            aliases,
            run_id="run_same_title",
            settings=QueryBuilderSettings(
                languages=["en", "zh-CN"], sources=["bilibili"], intents=["general"], max_per_source_intent=1,
            ),
            generated_at=NOW,
        )
        self.assertEqual({plan.language for plan in plans}, {"en", "zh-CN"})

    def test_high_ambiguity_alias_never_appears_alone(self):
        plans = self.build(languages=["en"], sources=["reddit"], intents=["general"], cap=5)
        tof = next(plan for plan in plans if "TOF" in plan.query_text)
        self.assertIn("Tower of Fantasy", tof.query_text)
        self.assertTrue(tof.disambiguators)

    def test_pending_alias_is_never_used(self):
        plans = self.build(languages=["en"], sources=["reddit"], intents=["general"], cap=10)
        self.assertFalse(any("Shirli" in plan.query_text for plan in plans))

    def test_intents_generate_distinct_plans(self):
        plans = self.build(
            languages=["en"], sources=["official"], intents=["performance", "controls", "patch"], cap=1,
        )
        self.assertEqual({plan.intent.value for plan in plans}, {"performance", "controls", "patch"})
        self.assertEqual(len({plan.query_text for plan in plans}), 3)
        patch = next(plan for plan in plans if plan.intent.value == "patch")
        self.assertEqual(patch.expected_evidence_kind.value, "patch_note")

    def test_steam_uses_app_identity(self):
        plans = self.build(languages=["en"], sources=["steam"], intents=["performance"], cap=5)
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0].query_text, "steam_app:2064650 intent:performance")
        self.assertEqual(plans[0].expected_evidence_kind.value, "review")

    def test_normalization_duplicate_aliases_do_not_duplicate_plans(self):
        aliases = alias_result()
        base = next(alias for alias in aliases.aliases if alias.text == "Tower of Fantasy")
        aliases.aliases.append(
            GameAlias(
                alias_id="alias_duplicate", game_id=base.game_id, text=" tower  of fantasy ",
                normalized_text=base.normalized_text, language="en", alias_type="localized_title",
                source_evidence_ids=["ev_duplicate"], source_platforms=["all"], confidence=1,
                ambiguity="none", validation_status="validated", search_enabled=True,
                standalone_search_safe=True,
            )
        )
        plans = build_query_plans(
            game(), aliases, run_id="run_test",
            settings=QueryBuilderSettings(languages=["en"], sources=["reddit"], intents=["general"], max_per_source_intent=10),
            generated_at=NOW,
        )
        matching = [plan for plan in plans if plan.alias_ids[0] in {base.alias_id, "alias_duplicate"}]
        self.assertEqual(len(matching), 1)

    def test_query_caps_are_deterministic(self):
        first = self.build(languages=["en"], sources=["reddit"], intents=["general"], cap=1)
        second = self.build(languages=["en"], sources=["reddit"], intents=["general"], cap=1)
        self.assertEqual(len(first), 1)
        self.assertEqual([plan.to_dict() for plan in first], [plan.to_dict() for plan in second])

    def test_plans_serialize_with_required_links(self):
        plan = self.build(languages=["en"], sources=["official"], intents=["controls"], cap=1)[0]
        rebuilt = type(plan).from_dict(plan.to_dict())
        self.assertEqual(rebuilt.run_id, "run_test")
        self.assertEqual(rebuilt.game_id, game().game_id)
        self.assertTrue(rebuilt.alias_ids)

    def test_cli_previews_plans_without_collection(self):
        resolution = ResolutionResult(
            input_name="Tower of Fantasy", locale="en", status="resolved", game=game(), candidates=[],
            reasons=["fixture"], provider_failures=[], partial=False,
        )
        args = SimpleNamespace(
            game="Tower of Fantasy", locale="en", languages="en", sources="steam",
            intents="performance", max_per_source_intent=1,
        )
        output = io.StringIO()
        with patch("scripts.gamepulse.resolve_game", return_value=resolution), redirect_stdout(output):
            command_plan(args)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload[0]["query_text"], "steam_app:2064650 intent:performance")


if __name__ == "__main__":
    unittest.main()
