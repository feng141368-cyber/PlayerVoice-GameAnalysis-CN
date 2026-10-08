from __future__ import annotations

import html
from datetime import datetime
from typing import Any

from ..config import env
from ..http import CollectionError, request_json
from ..schema import record


API = "https://www.googleapis.com/youtube/v3"


def _video_ids(config: dict[str, Any], api_key: str) -> list[str]:
    ids = [str(item) for item in config.get("video_ids", [])]
    if ids or not config.get("query"):
        return ids
    payload = request_json(
        f"{API}/search",
        params={"part": "snippet", "type": "video", "q": config["query"],
                "maxResults": min(int(config.get("max_videos", 5)), 25), "key": api_key,
                "order": config.get("order", "relevance")},
    )
    return [item["id"]["videoId"] for item in payload.get("items", []) if item.get("id", {}).get("videoId")]


def collect_youtube(game: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    api_key = env(config.get("api_key_env", "YOUTUBE_API_KEY"))
    if not api_key:
        raise CollectionError("YouTube credential missing: set YOUTUBE_API_KEY")
    rows: list[dict[str, Any]] = []
    for video_id in _video_ids(config, api_key):
        token = None
        collected = 0
        limit = int(config.get("comments_per_video", 100))
        while collected < limit:
            params = {
                "part": "snippet,replies", "videoId": video_id, "maxResults": min(100, limit - collected),
                "order": config.get("comment_order", "relevance"), "textFormat": "plainText", "key": api_key,
            }
            if token:
                params["pageToken"] = token
            payload = request_json(f"{API}/commentThreads", params=params)
            for item in payload.get("items", []):
                top = item["snippet"]["topLevelComment"]["snippet"]
                comment_id = item["snippet"]["topLevelComment"]["id"]
                rows.append(
                    record(
                        source="youtube", source_type="social_comment", game=game, channel=video_id,
                        content_type="comment", source_content_id=comment_id, parent_id=None,
                        created_at=datetime.fromisoformat(top["publishedAt"].replace("Z", "+00:00")).isoformat(),
                        title=None, text=html.unescape(top.get("textDisplay", "")).strip(),
                        url=f"https://www.youtube.com/watch?v={video_id}&lc={comment_id}", language=None,
                        recommended=None, rating=None, engagement_score=int(top.get("likeCount", 0)),
                        reply_count=int(item["snippet"].get("totalReplyCount", 0)), playtime_hours=None,
                        metadata_json={"video_id": video_id, "updated_at": top.get("updatedAt")},
                    )
                )
                collected += 1
                if collected >= limit:
                    break
            token = payload.get("nextPageToken")
            if not token or not payload.get("items"):
                break
    return rows
