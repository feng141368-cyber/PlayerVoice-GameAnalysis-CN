# Normalized voice schema

Every collected item uses the same fields:

- Identity: `record_id`, `source`, `source_content_id`, `parent_id`
- Scope: `game`, `channel`, `source_type`, `content_type`
- Evidence: `title`, `text`, `url`, `language`
- Time: `created_at`, `collected_at`
- Native signals: `recommended`, `rating`, `engagement_score`, `reply_count`, `playtime_hours`
- Traceability: `metadata_json`

`record_id` is a stable hash of source and source content ID. The same source item replaces its previous version during incremental upsert. Do not use text hashes as the primary identity when a source ID exists.

Omit profile names and raw account identifiers unless a legitimate analysis need is stated and approved.
