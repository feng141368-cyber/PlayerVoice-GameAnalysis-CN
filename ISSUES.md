# PlayerVoice implementation backlog

This backlog is ordered by dependency. Each block can be copied into a GitHub Issue. P0/P1 Issues include executable acceptance tests and a Definition of Done. P2/P3 preserve the architecture without expanding the seven-day MVP.

## Labels and milestones

- Priorities: `P0-contract`, `P1-core`, `P2-mode`, `P3-backlog`
- Areas: `resolver`, `aliases`, `query`, `facts`, `source-adapter`, `relevance`, `corpus`, `taxonomy`, `evidence`, `mode`, `patch`, `private-data`
- Milestone: `7-day-mvp` for Issues 1–10
- Milestone: `post-mvp` for Issues 11–17

## Seven-day execution order

| Day | Primary Issues | Deliverable |
| --- | --- | --- |
| 1 | 1–2 | typed contracts and canonical resolver |
| 2 | 3–4 | validated aliases and query matrix |
| 3 | 5 | Fact Layer vertical slice |
| 4 | 6 | source adapter contract; Steam/Bilibili migration |
| 5 | 7–8 | relevance plus corpus/evidence store |
| 6 | 9–10 | cross-game UGC and evidence-linked insights |
| 7 | integration/e2e hardening | three-game demo, docs, failures, CI |

---

## Issue 1 — Define typed domain contracts and compatibility mapping

Labels: `P0-contract`, `evidence`, `7-day-mvp`

Depends on: none

Goal: turn `DATA_SCHEMA.md` into validated models without changing collection behaviour.

Copilot implementation prompt:

> Read `SPECIFICATION.md`, `ARCHITECTURE.md`, `DATA_SCHEMA.md`, and `config/taxonomy.yaml` completely. Introduce typed models for GameEntity, GameAlias, FactRecord, QueryPlan, EvidenceItem, AnalysisAnnotation, Insight, PatchRecord, PrivateDataset, and CollectionRun. Prefer Pydantic or dataclasses plus explicit validators; choose one approach and document it. Create JSON Schemas for GameEntity, FactRecord, EvidenceItem, Insight, and CollectionRun. Add a compatibility converter from the current normalized voice row into EvidenceItem so the existing 327-record sample remains readable. Do not migrate collectors, rename the package, or implement modes in this Issue. Do not store credentials or new personal identifiers.

Acceptance tests:

- A valid fixture for each model round-trips through serialization.
- A `high`-ambiguity alias with `standalone_search_safe: true` is rejected.
- A rejected alias with `search_enabled: true` is rejected.
- A public EvidenceItem with required fields validates.
- A private EvidenceItem without `dataset_id` is rejected.
- An Insight with zero evidence links is rejected.
- Current `data/processed/voice.csv` converts without losing source ID, text, URL/reference, timestamps, rating/recommendation, or engagement signals.
- JSON Schemas are deterministic and checked into `schemas/`.

Definition of Done:

- Models and schema files match `DATA_SCHEMA.md` or deviations are documented in an ADR note.
- New unit tests pass in CI alongside all existing tests.
- No collector behaviour or report output changes.
- Public/private access scope is explicit and defaults do not expose private data.

---

## Issue 2 — Build canonical Game Resolver with candidate handling

Labels: `P0-contract`, `resolver`, `7-day-mvp`

Depends on: 1

Goal: resolve free-text names into one canonical entity or return candidates instead of silently choosing the wrong game.

Copilot implementation prompt:

> Implement Game Resolver using the new GameEntity model. Wrap existing Wikidata and Steam discovery behind resolver providers. Candidate ranking must consider exact/localized title match, external IDs, developer/publisher context, platform presence, and locale; string similarity alone is insufficient. Return `resolved`, `needs_choice`, or `unresolved`, with candidate reasons and evidence references. Cache provider responses locally by normalized input and locale. Preserve the existing `discover --game` path through a compatibility layer. Do not perform community retrieval or alias expansion in the resolver.

Acceptance tests:

- `无限暖暖` resolves to the same entity as `Infinity Nikki` using fixtures.
- `Tower of Fantasy` and `幻塔` resolve to the same entity and retain both localized titles.
- An intentionally ambiguous short name returns `needs_choice` with at least two candidates and does not choose one.
- An unknown game returns `unresolved` without throwing an unhandled exception.
- Provider timeout returns a typed partial/unresolved result with a reason.
- Cached fixture mode produces deterministic tests without network access.

Definition of Done:

- Resolver exposes a stable function/service contract documented in its module.
- Candidate evidence and confidence are inspectable.
- Unit tests use fixtures; one optional integration test may use live metadata but is excluded from default CI.
- Existing name-first CLI behaviour remains available.

---

## Issue 3 — Implement alias discovery, validation, and ambiguity policy

Labels: `P0-contract`, `aliases`, `7-day-mvp`

Depends on: 1–2

Goal: discover useful multilingual aliases while preventing unsafe nickname expansion.

Copilot implementation prompt:

> Implement alias discovery as a separate service from resolution. Gather official/localized titles from resolved metadata and allow evidence-backed abbreviations, transliterations, community nicknames, and common misspellings. Every alias must populate source evidence, language, type, platform scope, confidence, ambiguity, validation status, `search_enabled`, and `standalone_search_safe`. Implement deterministic validation rules from `DATA_SCHEMA.md`. Co-occurrence alone must never produce a validated nickname. Add a reviewable output for pending/scoped aliases. Do not scrape new social sources in this Issue.

Acceptance tests:

- Official Chinese and English titles validate as standalone-safe.
- A high-ambiguity abbreviation is `scoped_only` or rejected and cannot generate a standalone query.
- A term observed only as a co-occurring character/feature name remains pending or rejected.
- Duplicate aliases differing only by normalization merge while retaining all source evidence.
- Platform-scoped nicknames retain their platform list.
- Alias provenance survives serialization.

Definition of Done:

- Alias rules are deterministic and documented.
- Tests cover official, nickname, abbreviation, misspelling, duplicate, and ambiguous cases.
- No unvalidated alias enters query generation by default.
- Resolver and alias responsibilities remain separate.

---

## Issue 4 — Generate multilingual, source-aware query plans

Labels: `P0-contract`, `query`, `7-day-mvp`

Depends on: 2–3

Goal: create an auditable query matrix from identity, language, source, and research intent.

Copilot implementation prompt:

> Implement Query Builder using QueryPlan. Support the intent list in `ARCHITECTURE.md`, with separate English and Chinese templates and source-specific strategies for official web sources, Steam, Reddit, and Bilibili. Use only validated/search-enabled aliases. Add disambiguators whenever an alias is not standalone-safe. Deduplicate semantically identical plans and cap configurable query counts per source/intent. Store exact query text, alias IDs, disambiguators, expected evidence kind, and generation time. The builder must not execute network requests.

Acceptance tests:

- A bilingual entity produces separate zh-CN and en plans.
- A high-ambiguity alias never appears alone.
- `performance`, `controls`, and `patch` produce distinct intent plans.
- Steam uses entity/app identity when available instead of broad web text queries.
- Duplicate aliases do not create duplicate QueryPlans.
- Query caps are enforced deterministically.

Definition of Done:

- Query plans serialize and link to game/run/alias IDs.
- Source templates are configuration-driven where practical.
- Unit tests require no network.
- CLI can preview query plans without collecting.

---

## Issue 5 — Add the official Fact Layer vertical slice

Labels: `P0-contract`, `facts`, `7-day-mvp`

Depends on: 1–2, 4

Goal: retrieve verified game facts separately from community evidence.

Copilot implementation prompt:

> Implement a Fact Layer adapter for official game/store pages and structured metadata already available to the project. Collect atomic FactRecords for titles, developer, publisher, release date, platforms, minimum/recommended requirements, storage, input support, supported languages, cross-play/cross-save when documented, current version, and official patch references. Each FactRecord must cite an EvidenceItem and preserve retrieval time, authority, territory/platform scope, and verification state. Conflicts remain visible. Do not infer undocumented support and do not use player posts as official facts.

Acceptance tests:

- Official/store fixtures produce separate FactRecords with evidence links.
- Minimum and recommended requirements remain distinct.
- Missing cross-save information produces no affirmative fact.
- Two conflicting sources create `conflicting` records rather than silent overwrite.
- Facts for different platforms/territories remain scoped.
- A mode can retrieve facts without loading UGC analysis.

Definition of Done:

- Fact Layer has at least one live-capable adapter and deterministic fixtures.
- Every fact has source authority, evidence, retrieved time, and verification status.
- Fact and UGC records are stored/queryable separately.
- Integration test demonstrates a `Can I run it?` fact bundle without player claims.

---

## Issue 6 — Standardize source adapters and migrate Steam/Bilibili

Labels: `P1-core`, `source-adapter`, `7-day-mvp`

Depends on: 1, 4

Goal: make retrieval pluggable without rewriting working collectors.

Copilot implementation prompt:

> Define SourceAdapter, SourceCapabilities, SourcePage, and RetrievalContext contracts from `ARCHITECTURE.md`. Wrap/migrate the existing Steam and Bilibili collectors behind this interface while preserving pagination, conservative delays, retries, and current normalized content. Add an `official` adapter boundary and keep Reddit compatible for subsequent use. Add stub capability descriptors—not fake collectors—for TapTap, Weibo, Xiaohongshu, Douyin, App Store, and Google Play. Restricted stubs must return typed unavailable status. Do not add access-control bypasses.

Acceptance tests:

- Steam and Bilibili adapters pass the same contract test suite.
- Adapter capabilities declare evidence kinds, auth model, pagination, and supported query styles.
- Pagination preserves stable source IDs and cursor state.
- Empty/deleted content is excluded with a counted reason.
- A missing credential or provider endpoint returns `unavailable`, not an empty success.
- A restricted-platform stub performs no network request.

Definition of Done:

- Current live collection still works through adapter wrappers.
- Contract tests can be reused by every future adapter.
- Run manifests record source status and item counts.
- Existing rate-limit/retry safety remains intact.

---

## Issue 7 — Add relevance scoring and review queue

Labels: `P1-core`, `relevance`, `7-day-mvp`

Depends on: 2–4, 6

Goal: protect precision after alias/query expansion.

Copilot implementation prompt:

> Implement a deterministic baseline Relevance Engine producing `relevant`, `ambiguous`, or `irrelevant`, plus score and reasons. Features may include canonical/alias matches, developer/publisher, characters or game-specific terms, source entity context, platform/app ID, version/patch context, and negative evidence for competing entities. Source-native entity IDs should outweigh weak text matches. High-ambiguity alias-only results cannot be `relevant`. Store the method version. Provide a human-review CSV/JSON view for ambiguous records. Do not use sentiment in relevance scoring.

Acceptance tests:

- Correct Steam app-ID records are relevant even when the title is absent from text.
- A short ambiguous alias with no disambiguator is ambiguous, not relevant.
- A competing game sharing a token is irrelevant when entity evidence points elsewhere.
- Relevance reasons name the positive/negative evidence used.
- Threshold changes are configurable and method-versioned.
- Sentiment words do not affect relevance.

Definition of Done:

- Default corpus includes relevant records only.
- Ambiguous/irrelevant records remain counted and reviewable.
- Fixture precision/recall summary is printed in tests or evaluation output.
- Relevance version is stored with every evaluated record.

---

## Issue 8 — Build corpus, evidence store, and provenance isolation

Labels: `P1-core`, `corpus`, `evidence`, `7-day-mvp`

Depends on: 1, 5–7

Goal: create one traceable corpus while isolating public and private namespaces.

Copilot implementation prompt:

> Implement a local Evidence Store and Corpus Builder using SQLite plus JSONL raw snapshots, or justify a simpler equivalent. Upsert by source/source_content_id; use content fingerprints only to mark likely cross-posts. Store run manifests, query links, relevance outcomes, provenance, and source-native signals. Public and private scopes must be separate at query time; uploads default to private and require a dataset ID. Provide read methods for facts, relevant UGC, ambiguous review queue, and evidence by ID. Do not add a vector database or server.

Acceptance tests:

- Re-running the same source item updates/deduplicates rather than doubles counts.
- Two platforms carrying the same text remain separate evidence items but may share a cross-post fingerprint.
- Default public query returns no private items.
- Querying private items requires the matching dataset/owner scope.
- An evidence ID resolves to original text plus provenance and run/query references.
- Partial source failure still commits successful sources and a truthful manifest.

Definition of Done:

- Evidence lookup supports Insight traceability.
- Public/private isolation tests pass.
- Storage migration/version is documented.
- Existing sample can be imported and validated.

---

## Issue 9 — Implement cross-game multi-label UGC annotations

Labels: `P1-core`, `taxonomy`, `7-day-mvp`

Depends on: 1, 7–8

Goal: replace the single hard-coded topic classifier with a versioned core + genre-extension taxonomy.

Copilot implementation prompt:

> Load and validate `config/taxonomy.yaml`. Implement a transparent baseline annotator that assigns one primary topic and optional secondary topics, separately from sentiment and behaviour signals. Activate genre extensions from GameEntity genres/tags but always retain comparable core topic IDs. Preserve source-native recommendation/rating independently. Add `mixed` and `unknown` sentiment. Extract explicit feature requests separately from inferred needs. Version every annotation. Keep the baseline inspectable; do not add opaque model dependencies in this Issue.

Acceptance tests:

- One review may receive combat primary plus controls secondary.
- A negative performance review is not classified as a monetisation issue solely because it mentions price in passing.
- Source-native Steam recommendation remains unchanged when inferred sentiment differs.
- Gacha/MMO extension topics appear only when the relevant extension is active.
- Core topics can compare two games with different extensions.
- `other_unclassified` is never promoted to a priority.
- Behaviour signals require explicit cues and are labelled as expressed intent, not observed behaviour.

Definition of Done:

- Taxonomy validation fails clearly on duplicate IDs or missing labels.
- Annotation output includes taxonomy and method versions.
- Bilingual fixtures cover core and at least two extensions.
- Existing sample can be re-annotated without losing evidence references.

---

## Issue 10 — Produce evidence-linked insights and truthful coverage

Labels: `P1-core`, `evidence`, `7-day-mvp`

Depends on: 5, 7–9

Goal: complete the core vertical slice from a game name to verifiable findings.

Copilot implementation prompt:

> Implement Insight Engine over FactRecords, relevant EvidenceItems, and AnalysisAnnotations. Generate bounded praise, complaint, controversy, difference, research-gap, and analyst opportunity records. Every Insight must include supporting evidence, optional challenging evidence, sample scope, confidence, and uncertainty. Priority combines explicit dimensions such as volume, negative share, momentum, and source breadth, and must be labelled decision support—not causal effect. Generate a coverage report listing collected/partial/unavailable/disabled sources, date ranges, languages, and exclusions. Update report rendering to follow evidence IDs back to the original source/reference.

Acceptance tests:

- Creating an Insight without evidence fails validation.
- A controversy includes at least two distinguishable positions or is downgraded to an open question.
- An unavailable source appears in coverage and contributes neither zeros nor negative evidence.
- Source-native and inferred sentiment methods are labelled separately.
- Priority output includes component scores and the decision-support disclaimer.
- A report evidence link resolves to stored original content.
- Fact statements and player reports are visibly labelled and not merged.

Definition of Done:

- Name → resolve → query → collect → relevance → corpus → annotate → insight works for three fixture games.
- At least one live demo uses two community sources plus official facts where access permits.
- CI validates evidence integrity and manifest/report count agreement.
- README status table accurately distinguishes implemented and planned features.

---

## Issue 11 — Define and implement thin Mode API/router

Labels: `P2-mode`, `mode`, `post-mvp`

Depends on: 10

Copilot implementation prompt:

> Implement the common request/response contract in `ARCHITECTURE.md` and route requests to Player, Creator, Analyst, or Compare renderers. Validate mode-specific requirements, especially two or more games for Compare and authorisation for private datasets. Reuse one corpus and Insight Engine; do not duplicate collection pipelines. Return coverage, limitations, generated_at, and evidence references for every mode. Initially allow Analyst to expose only supported baseline sections.

Expected result: mode contract tests demonstrate shared core reuse and clear validation errors.

---

## Issue 12 — Player Mode evidence-based fit report

Labels: `P2-mode`, `mode`, `post-mvp`

Depends on: 5, 10–11

Copilot implementation prompt:

> Implement Player Mode sections from `SPECIFICATION.md`. Build a structured PreferenceProfile and map preferences to taxonomy nodes. Separate official facts from player reports in `Can I run it?`, `Where can I play it?`, `How does it play?`, and `Look and sound`. Produce likely matches, possible friction, things to consider, uncertainty, and evidence. Never emit a universal numeric recommendation or convert missing evidence into neutral fit.

Expected result: a fixture user who likes exploration/characters, dislikes PvP/high daily commitment, and prioritises combat receives explainable matches/frictions with evidence IDs.

---

## Issue 13 — Creator Research Brief

Labels: `P2-mode`, `mode`, `post-mvp`

Depends on: 10–11

Copilot implementation prompt:

> Implement Creator Mode as a research brief, not a finished review script. Include game/update context, praise, complaints, controversies with positions, questions worth investigating, open questions, research gaps, community/platform differences where comparable, and representative evidence. Enforce minimum evidence and community breadth before asserting a controversy or China/global difference.

Expected result: every brief section is either evidence-backed or explicitly marked insufficient evidence.

---

## Issue 14 — Basic Compare Mode

Labels: `P2-mode`, `mode`, `post-mvp`

Depends on: 5, 9–11

Copilot implementation prompt:

> Implement comparison across two to four games using core taxonomy IDs and common fact dimensions. Normalize by corpus size/time window where appropriate, show raw sample counts and source mix, and preserve extension-specific detail. Apply an optional PreferenceProfile to produce per-game likely matches and possible friction. Mark dimensions non-comparable when facts, time windows, or source coverage are materially different. Do not compute one winner score.

Expected result: a three-game comparison explains differences and evidence gaps without ranking missing data as average.

---

## Issue 15 — Advanced Analyst Mode

Labels: `P3-backlog`, `mode`, `post-mvp`

Depends on: 10–11

Copilot implementation prompt:

> Extend Analyst Mode with the full chain raw statement → pain point → underlying need → behaviour signal → business-impact hypothesis → product opportunity → priority. Keep explicit feature requests separate from inferred opportunities. Add segment, source, version, and time-window slicing. Require evidence, confidence, and uncertainty for every inference and label business impacts as hypotheses unless authorised behavioural data is joined.

---

## Issue 16 — Patch Intelligence

Labels: `P3-backlog`, `patch`, `post-mvp`

Depends on: 5, 8–10

Copilot implementation prompt:

> Implement PatchRecord ingestion from official sources, atomic change-item taxonomy mapping, and configurable pre/post windows. Compare normalized topic share, sentiment method, pain points, bugs, performance complaints, and expressed behaviour signals while reporting source-mix shifts and sample sizes. Link apparent addressed complaints to patch change items and identify new post-patch issues. Enforce non-causal language unless an external causal design is explicitly supplied.

---

## Issue 17 — Authorised Private Data Ingestion

Labels: `P3-backlog`, `private-data`, `post-mvp`

Depends on: 1, 8, 11

Copilot implementation prompt:

> Implement validated CSV, JSON, and Excel ingestion into a private dataset namespace. Require authorisation attestation, schema mapping, owner scope, allowed modes, and retention policy. Default all uploads to private; exclude them from public corpus queries, examples, caches, and reports. Support combined public/private analysis only when explicitly requested, with evidence labels preserved. Add deletion hooks and audit-friendly manifests. Never infer permission from file accessibility alone.

---

## Release gate for the seven-day MVP

The MVP is ready only when Issues 1–10 satisfy their Definitions of Done and the following end-to-end cases pass:

1. English title → canonical entity → Chinese alias → bilingual query plans.
2. Chinese title → same canonical entity as its English title.
3. Ambiguous nickname → candidate/scoped query, never silent wrong resolution.
4. Official requirements and player performance reports appear as different layers.
5. Steam/Bilibili or another permitted two-source corpus produces relevant evidence and linked insights.
6. Missing Reddit/YouTube/restricted-platform access is visible as unavailable.
7. Repeated collection deduplicates by stable source ID.
8. Every insight resolves to original evidence and provenance.
9. Three fixture games complete offline in CI.
10. No test or documentation claims P2/P3 features are implemented before they are.
