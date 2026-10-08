# Approved provider contract

GamePulse uses this small HTTP contract to connect approved Weibo, Xiaohongshu, or Douyin data providers without binding the project to a specific vendor.

## Request

The adapter makes a `GET` request with:

- `query`: resolved game name or platform-specific alias;
- `limit`: requested maximum number of records;
- `Authorization: Bearer <token>` when a token is configured.

All names are configurable through YAML (`query_param`, `limit_param`, `token_header`, and `token_prefix`). Extra fixed parameters may be supplied under `params`.

## Response

The default response is:

```json
{
  "items": [
    {
      "id": "platform-stable-id",
      "text": "comment text",
      "created_at": "2026-09-20T12:00:00+08:00",
      "url": "https://source.example/item/123",
      "title": "optional parent title",
      "channel": "optional channel or author-anonymized bucket",
      "engagement": 12,
      "reply_count": 2,
      "content_type": "comment"
    }
  ]
}
```

`id`, `text`, and `created_at` are required. Nested vendor fields can be mapped with dotted paths:

```yaml
weibo:
  enabled: true
  endpoint_env: WEIBO_PROVIDER_ENDPOINT
  token_env: WEIBO_ACCESS_TOKEN
  items_path: data.comments
  mapping:
    id: comment.id
    text: comment.content
    created_at: comment.published_at
    engagement: metrics.likes
```

Providers may also return a JSON array directly. GamePulse stores the provider name and actual search query in `metadata_json`, but never writes the access token.

## Access boundary

Use only endpoints and exports you are authorized to access. The adapter does not automate login, reuse browser cookies, solve CAPTCHA, rotate identities, or evade rate limits. When access is absent, the run manifest records the source as `unavailable`.
