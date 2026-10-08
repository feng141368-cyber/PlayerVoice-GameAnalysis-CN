from .base import (
    AdapterRunResult,
    RetrievalContext,
    SourceAdapter,
    SourceCapabilities,
    SourcePage,
    SourceStatus,
    collect_all_pages,
)
from .steam import SteamReviewsAdapter, collect_steam, collect_steam_result
from .reddit import RedditAdapter, collect_reddit
from .youtube import collect_youtube
from .community_export import collect_community_export
from .bilibili import BilibiliCommentsAdapter, collect_bilibili, collect_bilibili_result
from .licensed_provider import collect_douyin, collect_weibo, collect_xiaohongshu
from .official import OfficialSourceAdapter
from .stubs import RestrictedPlatformAdapter, restricted_adapter_registry

__all__ = [
    "collect_steam", "collect_reddit", "collect_youtube", "collect_bilibili",
    "collect_weibo", "collect_xiaohongshu", "collect_douyin", "collect_community_export",
    "AdapterRunResult", "RetrievalContext", "SourceAdapter", "SourceCapabilities", "SourcePage",
    "SourceStatus", "collect_all_pages", "SteamReviewsAdapter", "BilibiliCommentsAdapter",
    "RedditAdapter", "OfficialSourceAdapter", "RestrictedPlatformAdapter", "restricted_adapter_registry",
    "collect_steam_result", "collect_bilibili_result",
]
