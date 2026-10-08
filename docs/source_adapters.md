# Source adapter contract

Issue 6 introduces a common boundary for community retrieval without changing
the resolver, alias, query, or Fact Layer contracts.

## Contract

Every adapter declares `SourceCapabilities` and implements:

- `search(QueryPlan, cursor) -> SourcePage` for source-native retrieval;
- `normalize(native_item, RetrievalContext) -> EvidenceItem` for the shared
  evidence envelope;
- typed `unavailable` status when a required identity, credential, or
  authorised endpoint is absent.

`RetrievalContext` persists the original game input, canonical `game_id`, full
query identity, intent, language, source, alias IDs, exact submitted query, and
retrieval timestamp. Normalized evidence stores that block as
`source_metadata.query_provenance`.

Pagination is bounded and cursor-cycle safe. Stable evidence IDs derive from
`source + source_content_id`, not page position. Empty/deleted content and
records without stable IDs are excluded with counted reasons.

## Implemented adapters

| Source | Live | Pagination | Authentication | Notes |
| --- | --- | --- | --- | --- |
| Steam reviews | yes | native cursor | none | Requires canonical Steam app ID. |
| Bilibili comments | yes, access permitting | composite search/video/comment cursor | none | Public endpoints may be regionally unavailable or rate limited. |
| Reddit | compatible wrapper | bounded listing | OAuth client credentials | Native pagination migration is deferred. |
| Official | boundary only | none | adapter-specific | Fact retrieval remains in the separate Fact Layer; no generic page scraper. |

Steam and Bilibili retain backward-compatible legacy row wrappers so the
existing `collect` CLI and CSV pipeline continue to work. Run manifests now
record query/request/item counts and exclusions for migrated adapters.

## Restricted capability stubs

TapTap, Weibo, Xiaohongshu, Douyin, App Store, and Google Play expose honest
capability descriptors only. Their stubs make no network request and return
`unavailable`. Authorised exports or licensed provider adapters remain the
permitted extension route; the project does not automate login, browser cookie
reuse, CAPTCHA solving, or access-control bypasses.
