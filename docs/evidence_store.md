# Evidence Store and corpus policy

Issue 8 introduces a local SQLite Evidence Store plus JSONL retrieval snapshots.
The schema version is `1` and is stored in `store_meta`; an unknown version
fails explicitly instead of being silently rewritten.

## Identity and deduplication

- The primary retrieval identity is access scope + dataset + source +
  `source_content_id`.
- Re-running the same source item updates it and increments the duplicate count
  rather than creating another player record.
- One item found by several query plans has one evidence row plus several
  `evidence_query_links`, preserving each query, intent, language, aliases, and
  run reference.
- A normalized-content SHA-256 fingerprint marks likely cross-posts. Identical
  text on Steam and Reddit remains two evidence items because platform identity
  and provenance differ.
- Text similarity alone never merges two distinct player records.

## Scope isolation

Public evidence is the only default query namespace. Private evidence requires
a registered, authorised `PrivateDataset`, exact `dataset_id`, and matching
`owner_scope` for both listing and ID lookup. User uploads are rejected if they
are not private. Private JSONL snapshots are written under a dataset-specific
directory and are never returned by public corpus methods.

## Read boundaries

The store exposes separate methods for:

- relevant public UGC;
- ambiguous public review records;
- evidence lookup by ID with original text/provenance/run/query links;
- scoped private evidence;
- atomic fact records;
- collection manifests.

Only `relevant` public UGC enters `CorpusBuilder.default_public_corpus`.
Ambiguous/irrelevant records remain stored and counted. Successful sources are
committed even when another source is partial or unavailable; the original
source status remains visible in the stored run manifest.

## Migration

`import_legacy_voice_sample` validates and imports the existing normalized CSV
through the same `EvidenceItem` compatibility mapping. The checked-in
327-record sample imports without evidence loss. Future schema changes must add
an explicit migration and increment `EVIDENCE_STORE_SCHEMA_VERSION`; v1 has no
automatic destructive migration.
