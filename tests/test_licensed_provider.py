import os
import unittest
from unittest.mock import patch

from gamepulse.collectors.licensed_provider import collect_douyin, collect_weibo


class LicensedProviderTests(unittest.TestCase):
    @patch("gamepulse.collectors.licensed_provider.request_json")
    def test_provider_uses_alias_and_maps_nested_fields(self, request_json):
        request_json.return_value = {
            "data": {
                "comments": [
                    {
                        "comment": {
                            "id": "w-1",
                            "body": "战斗手感很好",
                            "published": "2026-09-20T12:00:00+08:00",
                        },
                        "stats": {"likes": 9},
                    }
                ]
            }
        }
        config = {
            "endpoint": "https://provider.example/search",
            "query": "幻塔",
            "items_path": "data.comments",
            "mapping": {
                "id": "comment.id",
                "text": "comment.body",
                "created_at": "comment.published",
                "engagement": "stats.likes",
            },
        }
        rows = collect_weibo("Tower of Fantasy", config)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["game"], "Tower of Fantasy")
        self.assertEqual(rows[0]["engagement_score"], 9)
        self.assertIn('"search_query": "幻塔"', rows[0]["metadata_json"])
        self.assertEqual(request_json.call_args.kwargs["params"]["query"], "幻塔")

    @patch("gamepulse.collectors.licensed_provider.request_json")
    def test_provider_reads_endpoint_and_token_from_environment(self, request_json):
        request_json.return_value = []
        with patch.dict(
            os.environ,
            {"DOUYIN_PROVIDER_ENDPOINT": "https://provider.example/douyin", "DOUYIN_ACCESS_TOKEN": "secret"},
            clear=False,
        ):
            rows = collect_douyin(
                "无限暖暖",
                {"endpoint_env": "DOUYIN_PROVIDER_ENDPOINT", "token_env": "DOUYIN_ACCESS_TOKEN"},
            )
        self.assertEqual(rows, [])
        self.assertEqual(request_json.call_args.kwargs["headers"]["Authorization"], "Bearer secret")


if __name__ == "__main__":
    unittest.main()
