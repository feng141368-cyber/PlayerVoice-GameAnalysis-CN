from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from .http import request_json
from .resolver import resolve_game


def resolve_game_aliases(game: str) -> dict[str, Any]:
    """Compatibility view for the existing name-first CLI.

    Issue 2 intentionally exposes only official/localized titles. Community alias
    discovery and validation are added by Issue 3.
    """

    language = "zh" if any(ord(char) > 127 for char in game) else "en"
    try:
        result = resolve_game(game)
        if result.status != "resolved" or result.game is None:
            return {"input": game, "english": game if language == "en" else None, "chinese": game if language == "zh" else None, "all": [game]}
        entity = result.game
        english = entity.localized_titles.get("en")
        chinese = entity.localized_titles.get("zh-CN") or entity.localized_titles.get("zh-cn") or entity.localized_titles.get("zh") or entity.localized_titles.get("zh-hans")
        aliases = [game, english, chinese, entity.canonical_title]
        unique = []
        for item in aliases:
            if item and item not in unique:
                unique.append(item)
        return {
            "input": game,
            "game_id": entity.game_id,
            "wikidata_id": entity.external_ids.get("wikidata_id"),
            "english": english,
            "chinese": chinese,
            "all": unique,
            "resolution_status": result.status.value,
        }
    except Exception:
        return {"input": game, "english": game if language == "en" else None, "chinese": game if language == "zh" else None, "all": [game]}


def resolve_steam_app(game: str, country: str = "US", language: str = "english") -> dict[str, Any] | None:
    payload = request_json(
        "https://store.steampowered.com/api/storesearch/",
        params={"term": game, "l": language, "cc": country},
        headers={"User-Agent": "GamePulse/0.2"},
    )
    candidates = payload.get("items") or []
    if not candidates:
        return None
    game_lower = game.casefold()
    ranked = sorted(
        candidates,
        key=lambda item: SequenceMatcher(None, game_lower, str(item.get("name", "")).casefold()).ratio(),
        reverse=True,
    )
    best = ranked[0]
    score = SequenceMatcher(None, game_lower, str(best.get("name", "")).casefold()).ratio()
    if score < 0.55:
        return None
    return {"app_id": int(best["id"]), "app_name": best["name"], "match_score": round(score, 3), "role": "focal"}


def build_runtime_config(game: str, *, steam_limit: int = 300) -> dict[str, Any]:
    aliases = resolve_game_aliases(game)
    steam_app = None
    for candidate in [aliases.get("english"), *aliases.get("all", [])]:
        if candidate:
            steam_app = resolve_steam_app(candidate)
            if steam_app:
                break
    community_query = aliases.get("english") or game
    chinese_query = aliases.get("chinese") or game
    sources: dict[str, Any] = {
        "steam": {"enabled": bool(steam_app), "apps": [steam_app] if steam_app else [], "limit_per_app": steam_limit,
                  "language": "english", "filter": "recent"},
        "bilibili": {"enabled": True, "query": chinese_query, "max_videos": 10, "comments_per_video": 50},
        "reddit": {"enabled": True, "subreddits": ["all"], "query": f'"{community_query}"', "limit_posts": 100,
                   "include_comments": True, "comments_per_post": 30},
        "youtube": {"enabled": True, "query": f"{community_query} review update", "max_videos": 8, "comments_per_video": 100},
        "weibo": {"enabled": True, "query": chinese_query, "endpoint_env": "WEIBO_PROVIDER_ENDPOINT", "token_env": "WEIBO_ACCESS_TOKEN"},
        "xiaohongshu": {"enabled": True, "query": chinese_query, "endpoint_env": "XIAOHONGSHU_PROVIDER_ENDPOINT", "token_env": "XIAOHONGSHU_PROVIDER_TOKEN"},
        "douyin": {"enabled": True, "query": chinese_query, "endpoint_env": "DOUYIN_PROVIDER_ENDPOINT", "token_env": "DOUYIN_ACCESS_TOKEN"},
    }
    return {"project": {"game": game, "aliases": aliases}, "sources": sources, "analysis": {"window_days": 30}}
