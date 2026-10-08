"""Declared support boundaries for platforms without general public comment APIs."""

PLATFORM_MODES = {
    "weibo": {
        "automatic_mode": "approved commercial/open API connector",
        "fallback_mode": "authorized CSV/JSON export",
        "reason": "General public post search and full comment access are permission-scoped.",
    },
    "xiaohongshu": {
        "automatic_mode": "licensed provider or user-authorized browser session",
        "fallback_mode": "authorized CSV/JSON export",
        "reason": "No stable general-purpose public search-and-comments API is advertised.",
    },
    "douyin": {
        "automatic_mode": "approved Douyin developer/game-partner access or licensed provider",
        "fallback_mode": "authorized CSV/JSON export",
        "reason": "Search and comment access depend on approved application scopes.",
    },
}
