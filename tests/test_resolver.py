from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gamepulse.discovery import build_runtime_config, resolve_game_aliases
from gamepulse.resolver import (
    FixtureResolverProvider,
    ResolutionContext,
    ResolverCache,
    SteamResolverProvider,
    resolve_game,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/resolver/catalog.json"


class TimeoutProvider:
    name = "timeout"

    def search(self, name: str, locale: str):
        raise TimeoutError("fixture timeout")


class ResolverTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache = ResolverCache(Path(self.temp_dir.name))
        self.provider = FixtureResolverProvider(FIXTURE)

    def tearDown(self):
        self.temp_dir.cleanup()

    def resolve(self, name: str, locale: str | None = None):
        return resolve_game(name, locale=locale, providers=[self.provider], cache=self.cache)

    def test_infinity_nikki_bilingual_names_resolve_to_same_entity(self):
        english = self.resolve("Infinity Nikki", "en")
        chinese = self.resolve("无限暖暖", "zh-CN")
        self.assertEqual(english.status.value, "resolved")
        self.assertEqual(chinese.status.value, "resolved")
        self.assertEqual(english.game.game_id, chinese.game.game_id)
        self.assertEqual(english.game.localized_titles["zh-CN"], "无限暖暖")
        self.assertEqual(chinese.game.localized_titles["en"], "Infinity Nikki")

    def test_tower_of_fantasy_bilingual_names_resolve_to_same_entity(self):
        english = self.resolve("Tower of Fantasy", "en")
        chinese = self.resolve("幻塔", "zh-CN")
        self.assertEqual(english.game.game_id, chinese.game.game_id)
        self.assertEqual(english.game.localized_titles["zh-CN"], "幻塔")
        self.assertEqual(chinese.game.localized_titles["en"], "Tower of Fantasy")

    def test_ambiguous_title_needs_choice(self):
        result = self.resolve("Prey", "en")
        self.assertEqual(result.status.value, "needs_choice")
        self.assertIsNone(result.game)
        self.assertGreaterEqual(len(result.candidates), 2)
        self.assertNotEqual(result.candidates[0].entity.game_id, result.candidates[1].entity.game_id)

    def test_unknown_game_is_unresolved(self):
        result = self.resolve("Definitely Not A Real Game", "en")
        self.assertEqual(result.status.value, "unresolved")
        self.assertIsNone(result.game)
        self.assertIn("no provider", result.reasons[0])

    def test_timeout_is_typed_unresolved_failure(self):
        result = resolve_game(
            "Example", locale="en", providers=[TimeoutProvider()], cache=self.cache,
        )
        self.assertEqual(result.status.value, "unresolved")
        self.assertEqual(result.provider_failures[0].error_type, "TimeoutError")
        self.assertIn("timeout", result.provider_failures[0].reason)

    def test_partial_resolution_keeps_provider_failure_visible(self):
        result = resolve_game(
            "Infinity Nikki", locale="en", providers=[self.provider, TimeoutProvider()], cache=self.cache,
        )
        self.assertEqual(result.status.value, "resolved")
        self.assertTrue(result.partial)
        self.assertEqual(result.provider_failures[0].provider, "timeout")

    def test_context_contributes_to_candidate_ranking(self):
        result = resolve_game(
            "Prey", locale="en", context=ResolutionContext(developer="Arkane Austin"),
            providers=[self.provider], cache=self.cache,
        )
        self.assertGreater(result.candidates[0].score, result.candidates[1].score)
        self.assertIn("developer context matched", result.candidates[0].reasons)

    def test_provider_responses_are_cached_by_normalized_input_and_locale(self):
        first = self.resolve("Infinity Nikki", "en")
        second = self.resolve("  infinity-nikki ", "en")
        self.assertEqual(first.game.game_id, second.game.game_id)
        self.assertEqual(self.provider.calls, 1)
        self.assertEqual(first.candidates[0].score, second.candidates[0].score)

    def test_existing_discover_compatibility_view_remains_available(self):
        resolved = self.resolve("Tower of Fantasy", "en")
        with patch("gamepulse.discovery.resolve_game", return_value=resolved):
            aliases = resolve_game_aliases("Tower of Fantasy")
        self.assertEqual(aliases["english"], "Tower of Fantasy")
        self.assertEqual(aliases["chinese"], "幻塔")

    def test_name_first_runtime_config_remains_available(self):
        with patch("gamepulse.discovery.resolve_game_aliases") as aliases, patch("gamepulse.discovery.resolve_steam_app") as steam:
            aliases.return_value = {
                "input": "Tower of Fantasy", "english": "Tower of Fantasy", "chinese": "幻塔",
                "all": ["Tower of Fantasy", "幻塔"],
            }
            steam.return_value = {"app_id": 2064650, "app_name": "Tower of Fantasy", "match_score": 1.0, "role": "focal"}
            config = build_runtime_config("Tower of Fantasy")
        self.assertEqual(config["project"]["game"], "Tower of Fantasy")
        self.assertEqual(config["sources"]["bilibili"]["query"], "幻塔")
        self.assertTrue(config["sources"]["steam"]["enabled"])

    def test_steam_provider_uses_locale_store_and_retains_bilingual_titles(self):
        calls = []

        def requester(url, **kwargs):
            calls.append((url, kwargs["params"]))
            if "storesearch" in url:
                return {"items": [{"id": 3164330, "name": "无限暖暖"}]}
            language = kwargs["params"]["l"]
            title = "无限暖暖" if language == "schinese" else "Infinity Nikki"
            return {
                "3164330": {
                    "success": True,
                    "data": {
                        "name": title,
                        "developers": ["Infold Games"],
                        "publishers": ["Infold Games"],
                        "platforms": {"windows": True},
                    },
                }
            }

        candidates = SteamResolverProvider(requester=requester).search("无限暖暖", "zh-CN")
        self.assertEqual(calls[0][1]["cc"], "CN")
        self.assertEqual(candidates[0].localized_titles["en"], "Infinity Nikki")
        self.assertEqual(candidates[0].localized_titles["zh-CN"], "无限暖暖")
        self.assertEqual(candidates[0].external_ids["steam_app_id"], "3164330")


if __name__ == "__main__":
    unittest.main()
