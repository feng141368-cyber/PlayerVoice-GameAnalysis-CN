# Issue 6–10 Implementation Review

This review is updated after each Issue. Work must stop after Issue 10 and the
three-game end-to-end validation.

## Issue status

### Issue 6 — Standardize source adapters and migrate Steam/Bilibili

- Status: completed
- Files changed: `gamepulse/collectors/base.py`, `steam.py`, `bilibili.py`,
  `reddit.py`, `official.py`, `collectors/stubs/*`, `collectors/__init__.py`,
  `gamepulse/collection.py`, `tests/test_source_adapters.py`, and
  `docs/source_adapters.md`.
- Functionality: typed adapter contracts/capabilities/status; normalized
  `EvidenceItem` output with complete query provenance; resumable Steam and
  Bilibili pagination; exclusion counts; official boundary; Reddit-compatible
  wrapper; no-network restricted-platform stubs; richer run manifests; legacy
  CSV/CLI wrappers preserved.
- Tests added: 7 adapter contract, pagination, exclusion, unavailable, network
  isolation, query provenance, and manifest tests.
- Test result: 64/64 passing (57 previous + 7 new); no Issue 1–5 regression.
- Known limitations: Reddit still uses one bounded legacy listing rather than a
  native resumable cursor. Bilibili public endpoints can be rate/region
  limited. Official retrieval remains in the existing Fact Layer. Restricted
  sources require authorised export or licensed-provider access.
- Deferred: relevance scoring, corpus persistence/deduplication, taxonomy, and
  insight generation belong to Issues 7–10.

### Issue 7 — Relevance scoring and review queue

- Status: completed
- Files changed: `gamepulse/relevance.py`, `tests/test_relevance.py`, and
  `docs/relevance.md`.
- Functionality: deterministic `relevant`/`ambiguous`/`irrelevant` decisions;
  source-native ID, official title, validated alias, developer/publisher,
  game-term, surrounding-context, query-provenance, and competing-entity
  signals; configurable thresholds; method/config hash; relevant-only corpus
  gate; CSV/JSON ambiguous review queue.
- Tests added: 10 tests covering Steam entity identity, high-ambiguity aliases,
  contextual CS2 evidence, competing entities, English/Chinese official names,
  configuration versions, sentiment independence, queue export, and fixture
  precision/recall.
- Test result: 74/74 passing (64 previous + 10 new); fixture baseline prints
  precision 1.00 / recall 1.00; no Issue 1–6 regression.
- Known limitations: deterministic rules need game-specific terms and competing
  entity fixtures for best precision; real-source quality still requires the
  manual E2E sample after Issue 10.
- Deferred: persistence, deduplication, and scope isolation belong to Issue 8.

### Issue 8 — Corpus, evidence store, and provenance isolation

- Status: completed
- Files changed: `gamepulse/evidence.py`, `gamepulse/corpus.py`,
  `tests/test_corpus.py`, and `docs/evidence_store.md`.
- Functionality: SQLite schema v1; public/private namespaces; authorised
  dataset/owner checks; user-upload private default enforcement; JSONL raw
  snapshots; source-ID upsert; exact-content cross-post fingerprints; multiple
  query links per one evidence item; separate fact/run storage; relevant UGC,
  ambiguous queue, scoped private, fact, run, and evidence-ID reads; legacy
  sample importer.
- Tests added: 10 tests for schema versioning, rerun deduplication,
  cross-platform fingerprints, query-link retention, public/private isolation,
  private upload enforcement, evidence traceback, partial-run commits, separate
  fact reads, and the full 327-record legacy import.
- Test result: 84/84 passing (74 previous + 10 new); no Issue 1–7 regression.
- Known limitations: fingerprints mark exact normalized cross-posts but do not
  auto-merge semantically similar posts; this avoids collapsing distinct
  players. Storage is single-process SQLite/JSONL by MVP design.
- Deferred: versioned UGC annotation belongs to Issue 9; insight aggregation
  and coverage rendering belong to Issue 10.

### Issue 9 — Cross-game multi-label UGC annotations

- Status: completed
- Files changed: `gamepulse/intelligence.py`, `tests/test_intelligence.py`, and
  `docs/ugc_annotations.md`.
- Functionality: validated taxonomy loader; stable core + genre extension
  activation; bilingual multi-label topic rules; separate inferred sentiment;
  explicit pain points, inferred needs, explicit feature requests, and
  expressed-intent behaviour signals; method/taxonomy/config versioning;
  annotation JSONL export; `other_unclassified` priority guard.
- Tests added: 14 tests covering validation failures, combat+controls
  multi-labeling, performance-vs-price specificity, source-native recommendation
  preservation, gacha/MMO activation, cross-extension core comparability,
  unclassified handling, Chinese churn/overheating, explicit feature requests,
  mixed/neutral/unknown sentiment, and all 327 legacy evidence links.
- Test result: 98/98 passing (84 previous + 14 new); no Issue 1–8 regression.
- Known limitations: the inspectable keyword baseline is deliberately not an
  opaque semantic model; sarcasm, implicit requests, and novel slang often need
  human review. Genre extensions vary in rule depth.
- Deferred: aggregation into bounded evidence-linked insights and truthful
  source coverage belongs to Issue 10.

### Issue 10 — Evidence-linked insights and truthful coverage

- Status: completed
- Files changed: `gamepulse/insights.py`, `gamepulse/voice_slice.py`,
  `gamepulse/corpus.py`, `gamepulse/intelligence.py`, `scripts/gamepulse.py`,
  `tests/test_insights.py`, `tests/test_voice_slice.py`, `docs/insights.md`,
  `README.md`, and `examples/e2e/*`.
- Functionality: one callable/CLI path composes Issues 1–10; bounded praise,
  complaint, controversy, difference, research-gap, and opportunity records;
  explicit evidence/challenging evidence, sample scope, confidence, and
  uncertainty; inspectable priority components and non-causal disclaimer;
  truthful source coverage; separate Fact and Player Evidence layers; JSONL
  annotation export; integrity validation; evidence-to-original-source report.
- Tests added: 12 Insight Engine tests plus 2 full-slice tests covering three
  fixture games and the scoped-CS2 query invariant.
- Test result: 112/112 passing (98 previous + 14 new); no Issue 1–9
  regression. The full suite includes the original 57 Issue 1–5 tests.
- Existing-module fix: live validation exposed double-counting of platform Fact
  evidence as community retrieval. `CorpusBuilder` now counts `fact_source`
  records in the separate official coverage bucket while retaining their real
  platform provenance. Community count semantics remain backward compatible.
- Known limitations: the transparent taxonomy has low recall for very short or
  slang-heavy posts; Steam's public review endpoint is entity-scoped rather
  than intent-searchable; a source URL may resolve to the app review listing
  while the native review ID remains stored; public samples are not population
  estimates.
- Deferred: Issue 11+ Mode routing, UI/dashboard, API server, vector database,
  personalised matching, advanced analyst priority, and patch causal analysis.

## Test results

| Checkpoint | Result |
| --- | ---: |
| Issue 1–5 baseline before this stage | 57/57 |
| After Issue 6 | 64/64 |
| After Issue 7 | 74/74 |
| After Issue 8 | 84/84 |
| After Issue 9 | 98/98 |
| After Issue 10 and three-game fixture integration | 112/112 |

Final command:

```bash
python -m unittest discover -s tests -v
```

Result: 112 tests passed, 0 failed, 0 skipped. A production-code scan found no
Infinity Nikki, PUBG, Counter-Strike 2, CS2, or app-ID constants in the runtime
modules/config. Game-specific literals remain only in fixtures, checked-in
validation artifacts, and filenames.

## Real end-to-end validation

The live runs used the Issue 1–5 resolver/facts, current public Steam review and
Bilibili routes, and the real Reddit adapter without credentials. No community
item was fabricated when a source failed.

| Game input | Canonical identity | Query plans successful | Raw community items | Raw relevance | Duplicate hits | Unique community items | Relevant corpus |
| --- | --- | ---: | ---: | --- | ---: | ---: | ---: |
| 无限暖暖 | `game_wikidata_q126199544` / 无限暖暖 / Infinity Nikki | 8/12 | 52 | 46 relevant, 6 irrelevant | 20 | 32 | 26 |
| PUBG: BATTLEGROUNDS | `game_steam_578080` | 5/12 | 43 | 40 relevant, 3 irrelevant | 20 | 23 | 20 |
| Counter-Strike 2 | `game_steam_730` | 6/12 | 46 | 40 relevant, 6 irrelevant | 30 | 16 | 10 |

“Duplicate hits” are repeated source items returned by different query plans.
The store keeps one evidence item and all corresponding query IDs/intents; it
does not count one player multiple times.

### Infinity Nikki

- Input `无限暖暖` resolved to one game entity with official Chinese title
  `无限暖暖`, English localized title `Infinity Nikki`, Steam app 3164330, and
  both aliases validated with evidence.
- The executed plans included Chinese and English routes: `无限暖暖`,
  `Infinity Nikki`, Chinese performance/bug terms, and entity-scoped Steam
  plans. Both languages remained under `game_wikidata_q126199544`.
- Steam: 4/4 plans collected, 40 raw review hits. Bilibili: 4/4 collected,
  12 comments, of which 6 passed relevance. Reddit: 0/4, explicitly unavailable
  because OAuth credentials were not configured. Official Fact Layer: 1 source
  evidence record supporting 11 facts.
- This is the live two-community-source plus official-facts demo required by
  Issue 10.

### PUBG: BATTLEGROUNDS

- Resolved to Steam app 578080. `PUBG` is retained as a medium-ambiguity,
  `scoped_only` alias and is not standalone-safe.
- Steam: 4/4 plans collected, 40 raw hits. Bilibili: 1/4 collected and 3/4
  returned HTTP 412; all 3 retrieved Bilibili items were generic performance
  discussions without PUBG identity and were excluded. Reddit: unavailable.
- The final relevant corpus therefore contains 20 unique Steam reviews, not
  unsupported Bilibili matches.

### Counter-Strike 2

- Resolved to Steam app 730. `CS2` is high ambiguity, `scoped_only`, and
  `standalone_search_safe=false`.
- Executed scoped plans include `CS2 Counter-Strike 2 Valve linux` and
  `"CS2" Counter-Strike 2 Valve linux`; there is no standalone `CS2` query.
- Steam: 4/4 plans collected, 40 raw hits. Bilibili: 2/4 collected and 2/4
  returned HTTP 412. The six returned Bilibili comments were excluded: three
  concerned Ghost Recon and three only established generic “CS” performance
  context, not Counter-Strike 2. Reddit: unavailable.
- The sample contains no Adobe CS2 or Cities: Skylines 2 false-positive corpus
  inclusion.

## Retrieval quality

| Game | Steam | Bilibili | Reddit | Official facts | Failed query plans |
| --- | --- | --- | --- | --- | ---: |
| Infinity Nikki | collected, 40 raw | collected, 12 raw | unavailable: credentials | collected, 11 facts | 4 |
| PUBG | collected, 40 raw | partial, 3 raw | unavailable: credentials | collected, 10 facts | 7 |
| Counter-Strike 2 | collected, 40 raw | partial, 6 raw | unavailable: credentials | collected, 10 facts | 6 |

Steam intent plans currently address the same entity endpoint and can return the
same reviews. This is why the deduplication/query-link contract is important.
Bilibili HTTP 412 responses are recorded as partial coverage; no anti-bot or
access-control bypass was attempted.

## Relevance quality

`examples/e2e/manual_relevance_review.json` contains a 30-item stratified
execution audit: ten items per game, inspecting text, parent title, source
identity, and canonical target outside the scorer.

- 18/18 sampled items admitted to the relevant corpus were manually confirmed:
  sampled corpus-inclusion precision 100%.
- Across all 30 stratified retrieved samples, 18 were manually relevant: 60%
  relevant yield. This denominator deliberately includes known negative and
  ambiguous stress cases and is not a random benchmark.
- Exact three-way label agreement was 27/30 (90%).
- There were zero sampled false-positive corpus inclusions.
- Three short `CS` Bilibili items were scored irrelevant but manually judged
  ambiguous. This is conservative exclusion, not false-positive inclusion.
- No live item landed in the automatic ambiguous queue, although the queue and
  high-ambiguity rules are covered by deterministic tests. More diverse live
  samples are needed to calibrate that boundary.

This was an execution review, not an independent third-party human benchmark.

## Corpus quality

| Game | Raw → unique | Relevant corpus | Unique platform distribution | Unique language distribution | Community date coverage |
| --- | --- | ---: | --- | --- | --- |
| Infinity Nikki | 52 → 32 | 26 | Steam 20, Bilibili 12 | zh-CN 22, en 10 | 2022-10-28 to 2026-10-02 |
| PUBG | 43 → 23 | 20 | Steam 20, Bilibili 3 | zh-CN 23 | 2026-09-14 to 2026-10-03 |
| Counter-Strike 2 | 46 → 16 | 10 | Steam 10, Bilibili 6 | zh-CN 16 | 2023-07-28 to 2026-10-03 |

The unique counts include relevant and excluded community items so the audit is
reproducible. Only the relevant subset reaches `annotations.jsonl` and Insight
generation. Fact evidence is stored and rendered separately.

## Insight examples and evidence traceback

All examples below resolve through the checked-in SQLite Evidence Store to
stored original text and source provenance.

| Structured result | Evidence | Original source |
| --- | --- | --- |
| Infinity Nikki story praise: 3 positive positions in a 5-item topic sample | `ev_229f5f8a617d92f761d9` includes “剧情个人挺喜欢的” | Steam app 3164330 review record |
| Infinity Nikki story complaint/controversy: 2 negative vs 3 positive positions | `ev_0f131e4cbbeb7e4e4148` plus three challenging positive IDs | Steam app 3164330 review records |
| Infinity Nikki explicit request: one-key story skip | `ev_2a50adf719624154de4b`, request text `能不能一键跳过。` | Steam app 3164330 review record |
| Infinity Nikki expressed-intent behaviour signals: churn risk, recommendation intent, feature request | `ev_2a50adf719624154de4b`; semantics explicitly say expressed intent, not observed behaviour | Steam app 3164330 review record |
| PUBG performance complaint | `ev_7262b3c1678ca794c2c5`, negative source-native recommendation | Steam app 578080 review record |
| CS2 gameplay praise | `ev_a22edf906b61b83269cd`, positive source-native recommendation | Steam app 730 review record |

The rendered reports place `Official facts (Fact Layer)` and `Player insights
(Player Evidence Layer)` in separate sections, then list every used evidence ID
in an `Evidence traceback` table. Priority fields expose volume, negative share,
momentum, source breadth, and the decision-support/non-causality disclaimer.

## Current failures and known limitations

- Reddit was not collected because credentials were absent. It is unavailable,
  not silently treated as zero sentiment.
- Bilibili returned HTTP 412 for some PUBG/CS2 searches. The runs are partial
  and retain the failure reasons; no workaround that bypasses access controls
  was added.
- Relevant Bilibili evidence was obtained only for Infinity Nikki in this run.
  PUBG and CS2 Insights therefore rely on Steam player evidence.
- The rule taxonomy left 13/26 Infinity Nikki, 18/20 PUBG, and 8/10 CS2 corpus
  items as `other_unclassified`. Short reviews and new slang need human review
  or a later, separately evaluated semantic method.
- The live scorer conservatively rejected three manually ambiguous `CS` items
  instead of placing them in the review queue. Threshold calibration remains
  future work.
- Steam retrieval is canonical-app scoped but not true intent search. Repeated
  intent plans improve provenance but may return the same review set.
- Exact duplicates are merged. Reliable cross-post fingerprints are recorded,
  but semantic near-duplicates are not automatically merged to avoid combining
  distinct players.
- Checked-in live evidence is a time-bounded public sample, not a population or
  causal estimate. Source availability and content will change on rerun.

## Real implementation boundary

Truly implemented and exercised:

- Issue 1–5 resolver, evidence-backed aliases, safe multilingual query plans,
  and official Fact Layer;
- Steam and Bilibili adapters, Reddit OAuth-aware unavailability, unified
  EvidenceItem normalization, and complete query provenance;
- deterministic relevance, review-queue support, SQLite corpus, deduplication,
  retained many-query provenance, public/private isolation;
- versioned taxonomy annotations with topics, sentiment, pain points, explicit
  requests, inferred needs, and expressed-intent behaviour signals;
- bounded Insight generation, truthful coverage, integrity validation, and
  Insight → Evidence → original source rendering.

Partially implemented:

- taxonomy coverage (stable core rules are real, but long-tail/slang recall is
  limited);
- Reddit adapter execution (real interface and credential checks, but no live
  credentialed result in this validation);
- Bilibili reliability (real successful collection plus recorded partial
  failures).

Interface/spec only or future work:

- restricted-platform adapters without authorised access;
- deeper genre-specific taxonomy breadth;
- all Issue 11+ Mode routers/renderers and product surfaces;
- dashboard, API server, vector database, recommendation/personalisation, and
  advanced causal/priority analysis.

## Architecture conclusion

The second vertical slice is real and executable:

`Query Plan → real community evidence → relevance gate → deduplicated corpus →
versioned annotation → evidence-linked Insight → original source`

It succeeds end to end for all three fixture identities and live Steam data,
and for Infinity Nikki it additionally reaches relevant Bilibili evidence while
preserving the same canonical game ID across Chinese and English queries. It is
not yet a broad platform-monitoring product: source access and taxonomy recall
remain explicit limitations. This checkpoint stops after Issue 10; Issue 11
has not been started.
