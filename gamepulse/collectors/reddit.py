from __future__ import annotations

import base64
import html
from datetime import datetime, timezone
from typing import Any, Iterable

from ..compatibility import normalized_voice_row_to_evidence
from ..config import env
from ..http import CollectionError, request_json
from ..models import EvidenceItem, QueryPlan
from ..schema import record
from .base import (
    ADAPTER_CONTRACT_VERSION,
    AuthModel,
    BaseSourceAdapter,
    PaginationModel,
    QueryStyle,
    RetrievalContext,
    SourceCapabilities,
    SourcePage,
    SourceStatus,
)


def _oauth_token(config: dict[str, Any]) -> str:
    client_id = env(config.get("client_id_env", "REDDIT_CLIENT_ID"))
    client_secret = env(config.get("client_secret_env", "REDDIT_CLIENT_SECRET"))
    if not client_id or not client_secret:
        raise CollectionError("Reddit credentials missing: set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET")
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    payload = request_json(
        "https://www.reddit.com/api/v1/access_token",
        data={"grant_type": "client_credentials"},
        headers={"Authorization": f"Basic {basic}", "User-Agent": config.get("user_agent", "GamePulse/0.2")},
    )
    if not payload.get("access_token"):
        raise CollectionError(f"Reddit OAuth did not return an access token: {payload}")
    return payload["access_token"]


def _flatten_comments(children: Iterable[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for child in children:
        if child.get("kind") != "t1":
            continue
        data = child.get("data", {})
        yield data
        replies = data.get("replies")
        if isinstance(replies, dict):
            yield from _flatten_comments(replies.get("data", {}).get("children", []))


def collect_reddit(game: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    token = _oauth_token(config)
    headers = {"Authorization": f"Bearer {token}", "User-Agent": config.get("user_agent", "GamePulse/0.2")}
    rows: list[dict[str, Any]] = []
    for subreddit in config.get("subreddits", []):
        params = {
            "limit": min(int(config.get("limit_posts", 100)), 100),
            "raw_json": 1,
            "sort": config.get("sort", "new"),
            "restrict_sr": 1,
        }
        query = config.get("query")
        endpoint = f"https://oauth.reddit.com/r/{subreddit}/new"
        if query:
            endpoint = f"https://oauth.reddit.com/r/{subreddit}/search"
            params["q"] = query
            params["t"] = config.get("time_filter", "year")
        listing = request_json(endpoint, params=params, headers=headers)
        posts = listing.get("data", {}).get("children", [])
        for child in posts:
            post = child.get("data", {})
            body = "\n\n".join(part for part in [post.get("title", ""), post.get("selftext", "")] if part).strip()
            if body:
                rows.append(
                    record(
                        source="reddit", source_type="community", game=game, channel=f"r/{subreddit}",
                        content_type="post", source_content_id=post["name"], parent_id=None,
                        created_at=datetime.fromtimestamp(post["created_utc"], tz=timezone.utc).isoformat(),
                        title=post.get("title"), text=html.unescape(body),
                        url=f"https://www.reddit.com{post.get('permalink', '')}", language="en",
                        recommended=None, rating=None, engagement_score=int(post.get("score", 0)),
                        reply_count=int(post.get("num_comments", 0)), playtime_hours=None,
                        metadata_json={"subreddit": subreddit, "flair": post.get("link_flair_text")},
                    )
                )
            if not config.get("include_comments", True):
                continue
            comments = request_json(
                f"https://oauth.reddit.com/comments/{post['id']}",
                params={"limit": min(int(config.get("comments_per_post", 50)), 100), "depth": 3, "sort": "top", "raw_json": 1},
                headers=headers,
            )
            for comment in _flatten_comments(comments[1].get("data", {}).get("children", [])):
                body = html.unescape(comment.get("body", "")).strip()
                if not body or body in {"[deleted]", "[removed]"}:
                    continue
                rows.append(
                    record(
                        source="reddit", source_type="community", game=game, channel=f"r/{subreddit}",
                        content_type="comment", source_content_id=comment["name"], parent_id=comment.get("parent_id"),
                        created_at=datetime.fromtimestamp(comment["created_utc"], tz=timezone.utc).isoformat(),
                        title=None, text=body,
                        url=f"https://www.reddit.com{post.get('permalink', '')}{comment['id']}/", language="en",
                        recommended=None, rating=None, engagement_score=int(comment.get("score", 0)),
                        reply_count=0, playtime_hours=None,
                        metadata_json={"subreddit": subreddit, "post_id": post["name"]},
                    )
                )
    return rows


class RedditAdapter(BaseSourceAdapter):
    """Compatibility wrapper for the existing OAuth collector.

    Native pagination migration is deferred; the wrapper already emits the
    common EvidenceItem contract and typed unavailable status through the
    shared orchestration layer.
    """

    name = "reddit"

    def __init__(self, config: dict[str, Any] | None = None, *, game_title: str | None = None) -> None:
        self.config = dict(config or {})
        self.game_title = game_title

    def capabilities(self) -> SourceCapabilities:
        return SourceCapabilities(
            source=self.name,
            evidence_kinds=["post", "comment"],
            auth_model=AuthModel.OAUTH_CLIENT_CREDENTIALS,
            pagination=PaginationModel.NONE,
            supported_query_styles=[QueryStyle.TEXT_SEARCH, QueryStyle.CHANNEL_SEARCH],
            languages=["en"],
            supported_intents=["*"],
            rate_limit={"retries": 3, "listing_limit_max": 100},
            live_retrieval=True,
            availability_notes="Requires Reddit client credentials; current wrapper performs one bounded listing.",
        )

    def search(self, plan: QueryPlan, cursor: str | None = None) -> SourcePage:
        config = {**self.config, "query": plan.query_text}
        rows = collect_reddit(self.game_title or plan.query_text, config)
        return SourcePage(
            source=self.name,
            status=SourceStatus.COLLECTED,
            cursor=cursor,
            native_items=rows,
            requests_made=1,
        )

    def normalize(self, native_item: dict[str, Any], context: RetrievalContext) -> EvidenceItem:
        item = normalized_voice_row_to_evidence(
            native_item,
            game_id=context.game_id,
            run_id=context.run_id,
        )
        metadata = dict(item.source_metadata)
        metadata["query_provenance"] = context.query_provenance
        provenance = item.provenance.model_copy(update={"collector_version": ADAPTER_CONTRACT_VERSION})
        return item.model_copy(
            update={
                "retrieved_at": context.retrieved_at,
                "query_id": context.query_plan.query_id,
                "matched_alias_ids": list(context.query_plan.alias_ids),
                "source_metadata": metadata,
                "provenance": provenance,
            }
        )
