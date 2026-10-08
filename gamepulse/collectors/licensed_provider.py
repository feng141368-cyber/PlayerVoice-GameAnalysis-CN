from __future__ import annotations

from typing import Any

from ..config import env
from ..http import CollectionError, request_json
from ..schema import record


def _get(item: dict[str, Any], path: str, default: Any = None) -> Any:
    value: Any = item
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return default
        value = value[part]
    return value


def collect_licensed_provider(game: str, platform: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect from an approved provider that returns mapped JSON items.

    This contract intentionally avoids assuming or bypassing a platform's private API.
    """
    endpoint = config.get("endpoint") or env(config.get("endpoint_env", f"{platform.upper()}_PROVIDER_ENDPOINT"))
    token = env(config.get("token_env", f"{platform.upper()}_PROVIDER_TOKEN"))
    if not endpoint:
        raise CollectionError(f"{platform} provider endpoint is not configured")
    headers = {"User-Agent": config.get("user_agent", "GamePulse/0.2")}
    if token:
        headers[config.get("token_header", "Authorization")] = f"{config.get('token_prefix', 'Bearer')} {token}".strip()
    query_param = config.get("query_param", "query")
    query = config.get("query") or game
    params = {
        query_param: query,
        config.get("limit_param", "limit"): int(config.get("limit", 500)),
        **config.get("params", {}),
    }
    payload = request_json(
        endpoint,
        params=params,
        headers=headers,
    )
    items: Any = payload
    if isinstance(payload, dict):
        for part in config.get("items_path", "items").split("."):
            items = items.get(part, []) if isinstance(items, dict) else []
    if not isinstance(items, list):
        raise CollectionError(f"{platform} provider response did not contain an item list")
    mapping = {
        "id": "id", "text": "text", "created_at": "created_at", "url": "url",
        "title": "title", "channel": "channel", "engagement": "engagement",
        "reply_count": "reply_count", "content_type": "content_type",
        **config.get("mapping", {}),
    }
    rows = []
    for item in items:
        content_id = _get(item, mapping["id"])
        text = str(_get(item, mapping["text"], "")).strip()
        created = _get(item, mapping["created_at"])
        if not content_id or not text or not created:
            continue
        rows.append(
            record(
                source=platform, source_type="licensed_provider", game=game,
                channel=str(_get(item, mapping["channel"], platform)),
                content_type=str(_get(item, mapping["content_type"], "comment")),
                source_content_id=str(content_id), parent_id=None,
                created_at=str(created), title=_get(item, mapping["title"]), text=text,
                url=_get(item, mapping["url"]), language=config.get("language", "zh-CN"),
                recommended=None, rating=None,
                engagement_score=int(_get(item, mapping["engagement"], 0) or 0),
                reply_count=int(_get(item, mapping["reply_count"], 0) or 0),
                playtime_hours=None,
                metadata_json={
                    "provider": config.get("provider_name", "approved-provider"),
                    "search_query": query,
                },
            )
        )
    return rows


def collect_weibo(game: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    return collect_licensed_provider(game, "weibo", config)


def collect_xiaohongshu(game: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    return collect_licensed_provider(game, "xiaohongshu", config)


def collect_douyin(game: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    return collect_licensed_provider(game, "douyin", config)
