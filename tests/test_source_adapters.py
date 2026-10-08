from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from gamepulse.collection import collect
from gamepulse.collectors.base import RetrievalContext, SourceStatus, collect_all_pages
from gamepulse.collectors.bilibili import BilibiliCommentsAdapter
from gamepulse.collectors.reddit import RedditAdapter
from gamepulse.collectors.steam import SteamReviewsAdapter
from gamepulse.collectors.stubs import restricted_adapter_registry
from gamepulse.models import QueryPlan


NOW = datetime(2026, 10, 3, tzinfo=timezone.utc)


def plan(source: str, query: str, *, language: str = "en", kind: str = "review") -> QueryPlan:
    return QueryPlan(
        query_id=f"query_{source}_test",
        run_id="run_adapter_test",
        game_id="game_counter_strike_2",
        source=source,
        language=language,
        intent="performance",
        query_text=query,
        alias_ids=["alias_cs2"],
        disambiguators=["Counter-Strike 2", "Valve"],
        expected_evidence_kind=kind,
        generated_at=NOW,
    )


def context(query_plan: QueryPlan) -> RetrievalContext:
    return RetrievalContext(
        original_game_input="CS2",
        game_id=query_plan.game_id,
        canonical_title="Counter-Strike 2",
        run_id=query_plan.run_id,
        query_plan=query_plan,
        retrieved_at=NOW,
    )


def steam_review(review_id: str, text: str) -> dict:
    return {
        "recommendationid": review_id,
        "review": text,
        "timestamp_created": 1_700_000_000,
        "voted_up": False,
        "votes_up": 4,
        "comment_count": 1,
        "author": {"steamid": f"author-{review_id}", "playtime_forever": 120},
    }


class SourceAdapterContractTests(unittest.TestCase):
    def test_steam_and_bilibili_share_capability_contract(self):
        adapters = [SteamReviewsAdapter({"app_id": 730}), BilibiliCommentsAdapter()]
        for adapter in adapters:
            with self.subTest(adapter=adapter.name):
                capabilities = adapter.capabilities()
                self.assertEqual(capabilities.source, adapter.name)
                self.assertTrue(capabilities.evidence_kinds)
                self.assertTrue(capabilities.auth_model.value)
                self.assertTrue(capabilities.pagination.value)
                self.assertTrue(capabilities.supported_query_styles)
                self.assertIn("request_delay_seconds", capabilities.rate_limit)

    @patch("gamepulse.collectors.steam.time.sleep", return_value=None)
    @patch("gamepulse.collectors.steam.request_json")
    def test_steam_pagination_keeps_stable_ids_and_cursor(self, request_json, _sleep):
        request_json.side_effect = [
            {"reviews": [steam_review("r1", "FPS fell after the update"), steam_review("r2", "Mirage stutters")], "cursor": "next"},
            {"reviews": [steam_review("r3", "Performance is smoother now")], "cursor": "next"},
        ]
        query_plan = plan("steam", "steam_app:730 intent:performance")
        result = collect_all_pages(
            SteamReviewsAdapter({"app_id": 730, "limit": 3, "request_delay_seconds": 0}),
            query_plan,
            context(query_plan),
        )
        self.assertEqual(result.status, SourceStatus.COLLECTED)
        self.assertEqual(result.pages_retrieved, 2)
        self.assertEqual([item.source_content_id for item in result.items], ["r1", "r2", "r3"])
        self.assertEqual(len({item.evidence_id for item in result.items}), 3)
        self.assertEqual(result.cursors[0], "<initial>")
        self.assertIn('"source_cursor":"next"', result.cursors[1])
        provenance = result.items[0].source_metadata["query_provenance"]
        self.assertEqual(provenance["original_game_input"], "CS2")
        self.assertEqual(provenance["actual_query"], query_plan.query_text)
        self.assertEqual(result.items[0].query_id, query_plan.query_id)

    @patch("gamepulse.collectors.steam.request_json")
    def test_empty_and_deleted_content_is_counted_not_normalized(self, request_json):
        request_json.return_value = {
            "reviews": [steam_review("empty", "  "), steam_review("deleted", "[deleted]"), steam_review("ok", "Real review")],
            "cursor": None,
        }
        query_plan = plan("steam", "steam_app:730 intent:performance")
        result = collect_all_pages(
            SteamReviewsAdapter({"app_id": 730, "limit": 3}),
            query_plan,
            context(query_plan),
        )
        self.assertEqual([item.source_content_id for item in result.items], ["ok"])
        self.assertEqual(result.excluded_counts, {"empty_or_deleted": 2})

    @patch("gamepulse.collectors.bilibili.time.sleep", return_value=None)
    @patch("gamepulse.collectors.bilibili.request_json")
    def test_bilibili_composite_cursor_is_resumable(self, request_json, _sleep):
        replies = [
            {"rpid_str": f"b{i}", "ctime": 1_700_000_000 + i, "content": {"message": f"第{i}条评论"}, "like": i, "rcount": 0}
            for i in range(21)
        ]

        def response(url, **kwargs):
            if "search/type" in url:
                return {"code": 0, "data": {"result": [{"aid": 1, "bvid": "BV1", "title": "CS2 更新"}]}}
            page_number = kwargs["params"]["pn"]
            return {"code": 0, "data": {"replies": replies[:20] if page_number == 1 else replies[20:]}}

        request_json.side_effect = response
        query_plan = plan("bilibili", '"CS2" Counter-Strike 2 Valve 性能', language="zh-CN", kind="comment")
        result = collect_all_pages(
            BilibiliCommentsAdapter({"comments_per_video": 25, "request_delay_seconds": 0}),
            query_plan,
            context(query_plan),
        )
        self.assertEqual(result.status, SourceStatus.COLLECTED)
        self.assertEqual(result.pages_retrieved, 2)
        self.assertEqual(len(result.items), 21)
        self.assertEqual(result.items[0].source_content_id, "b0")
        self.assertEqual(result.items[-1].source_content_id, "b20")
        self.assertIn('"comment_page":2', result.cursors[1])

    @patch.dict("os.environ", {}, clear=True)
    @patch("gamepulse.collectors.reddit.request_json")
    def test_missing_reddit_credentials_is_typed_unavailable(self, request_json):
        query_plan = plan("reddit", '"CS2" Counter-Strike 2 Valve performance', kind="post")
        result = collect_all_pages(
            RedditAdapter({"subreddits": ["GlobalOffensive"]}, game_title="Counter-Strike 2"),
            query_plan,
            context(query_plan),
        )
        self.assertEqual(result.status, SourceStatus.UNAVAILABLE)
        self.assertEqual(result.error_code, "collection_error")
        request_json.assert_not_called()

    @patch("urllib.request.urlopen")
    def test_restricted_stubs_never_make_network_requests(self, urlopen):
        for source, adapter in restricted_adapter_registry().items():
            with self.subTest(source=source):
                query_plan = plan(source, "game query", kind="post")
                result = collect_all_pages(adapter, query_plan, context(query_plan))
                self.assertEqual(result.status, SourceStatus.UNAVAILABLE)
                self.assertEqual(result.error_code, "restricted_platform")
                self.assertFalse(adapter.capabilities().live_retrieval)
        urlopen.assert_not_called()

    @patch("gamepulse.collectors.steam.request_json")
    def test_run_manifest_records_adapter_counts(self, request_json):
        request_json.return_value = {"reviews": [steam_review("manifest-1", "Playable but stutters")], "cursor": None}
        config = {
            "project": {"game": "Counter-Strike 2"},
            "sources": {
                "steam": {"enabled": True, "apps": [{"app_id": 730, "limit": 1}], "request_delay_seconds": 0},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            result = collect(config, Path(directory), selected={"steam"})
        source = result["sources"]["steam"]
        self.assertEqual(source["status"], "collected")
        self.assertEqual(source["items_retrieved"], 1)
        self.assertEqual(source["records"], 1)
        self.assertEqual(source["queries_attempted"], 1)
        self.assertEqual(source["excluded"], {})


if __name__ == "__main__":
    unittest.main()
