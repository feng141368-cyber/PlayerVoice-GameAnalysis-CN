from __future__ import annotations

import json
import unittest
from pathlib import Path

from pydantic import ValidationError

from gamepulse.modes import ModeRequest, load_core_snapshot, parse_preference_profile, route_mode


ROOT = Path(__file__).resolve().parents[1]
INFINITY = ROOT / "examples/e2e/infinity-nikki"


PREFERENCE_TEXT = (
    "我每天大概只能玩一个小时。"
    "我喜欢探索、剧情和角色塑造。"
    "我不喜欢重 PvP，也不喜欢每天必须上线做很多任务。"
    "比较在乎画面和音乐。"
)


class PlayerModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = load_core_snapshot(INFINITY)
        cls.pubg = load_core_snapshot(ROOT / "examples/e2e/pubg-battlegrounds")

    def test_natural_language_preferences_become_structured_profile(self):
        profile = parse_preference_profile(PREFERENCE_TEXT)
        self.assertEqual(profile.constraints["available_time_minutes_per_day"], 60)
        self.assertTrue({"exploration", "story", "characters", "graphics", "audio"}.issubset(profile.important))
        self.assertTrue({"pvp", "daily_commitment"}.issubset(profile.avoid))

    def test_player_report_separates_fact_and_player_evidence(self):
        response = route_mode(
            ModeRequest(
                request_id="request_player",
                mode="player",
                games=[self.snapshot.game.game_id],
                languages=["zh-CN", "en"],
                preferences=PREFERENCE_TEXT,
            ),
            [self.snapshot],
        )
        payload = response.payload
        self.assertTrue(any(value["layer"] == "fact" for value in payload["what_is_this_game"]))
        self.assertTrue(any(value["layer"] == "player_evidence" for value in payload["what_players_praise"]))
        self.assertTrue(all(value["fact_ids"] for value in payload["what_is_this_game"] if value["layer"] == "fact"))
        self.assertTrue(all(value["insight_ids"] and value["evidence_ids"] for value in payload["what_players_praise"] if value["layer"] == "player_evidence"))

    def test_fit_is_dimension_level_and_missing_evidence_stays_uncertain(self):
        response = route_mode(
            ModeRequest(
                request_id="request_fit",
                mode="player",
                games=[self.snapshot.game.game_id],
                preferences=PREFERENCE_TEXT,
            ),
            [self.snapshot],
        )
        fit = {item["dimension"]: item for item in response.payload["preference_fit"]}
        self.assertEqual(fit["story"]["assessment"], "likely_match")
        self.assertEqual(fit["pvp"]["assessment"], "uncertain")
        self.assertEqual(fit["daily_commitment"]["assessment"], "uncertain")
        self.assertEqual(fit["available_time"]["assessment"], "uncertain")
        self.assertEqual(fit["pvp"]["evidence_ids"], [])
        rendered = json.dumps(response.to_dict(), ensure_ascii=False).casefold()
        self.assertNotIn("recommendation score", rendered)
        self.assertNotIn("you should buy", rendered)

    def test_evidence_references_resolve_every_linked_claim(self):
        response = route_mode(
            ModeRequest(
                request_id="request_trace",
                mode="player",
                games=[self.snapshot.game.game_id],
                preferences=PREFERENCE_TEXT,
            ),
            [self.snapshot],
        )
        referenced = {item.evidence_id for item in response.evidence_references}
        linked = set()
        for section in [
            "what_is_this_game",
            "where_can_i_play_it",
            "can_i_run_it",
            "controls",
            "what_players_praise",
            "what_players_complain_about",
            "what_to_pay_attention_to",
        ]:
            for claim in response.payload[section]:
                linked.update(claim["evidence_ids"])
        for item in response.payload["preference_fit"]:
            linked.update(item["evidence_ids"])
        self.assertEqual(linked, referenced)
        self.assertTrue(all(item.source_url or item.source_reference for item in response.evidence_references))

    def test_controls_are_insufficient_not_neutral(self):
        response = route_mode(
            ModeRequest(
                request_id="request_controls",
                mode="player",
                games=[self.snapshot.game.game_id],
            ),
            [self.snapshot],
        )
        self.assertEqual(response.payload["controls"][0]["layer"], "insufficient")
        self.assertIn("not established", response.payload["controls"][0]["statement"])

    def test_mode_contract_rejects_compare_private_and_wrong_context(self):
        with self.assertRaisesRegex(ValidationError, "compare mode requires"):
            ModeRequest(request_id="bad_compare", mode="compare", games=["game_one"])
        with self.assertRaisesRegex(ValidationError, "private datasets are interface-only"):
            ModeRequest(
                request_id="private",
                mode="player",
                games=[self.snapshot.game.game_id],
                private_dataset_ids=["dataset_private"],
            )
        with self.assertRaisesRegex(ValueError, "no Intelligence Core snapshot"):
            route_mode(
                ModeRequest(request_id="wrong", mode="player", games=["game_wrong"]),
                [self.snapshot],
            )

if __name__ == "__main__":
    unittest.main()
