# Issue 1–5 Implementation Review

Review scope: the frozen `Game Name → Resolver → Alias → Query → Fact` foundation slice only. No Issue 6+ implementation is included.

## Outcome

The repository now has a usable foundation slice for Steam-listed games and games resolvable through the current metadata providers. A normal game-name input can resolve a canonical identity, retain official bilingual titles, validate evidence-backed aliases, create safe multilingual query plans and retrieve sourced store facts. Ambiguous or failed resolution stops downstream work rather than inventing data.

## Issue status and changed files

| Issue | Status | Main files | Verification |
| --- | --- | --- | --- |
| 1 — typed contracts | Complete | `gamepulse/models.py`, `gamepulse/compatibility.py`, `schemas/*.json`, `scripts/generate_schemas.py`, `docs/adr/0001-domain-contracts.md` | 10 model round-trips/constraints covered; all 327 legacy rows converted; generated schemas match checked-in files |
| 2 — canonical resolver | Complete | `gamepulse/resolver.py`, `gamepulse/discovery.py`, `tests/fixtures/resolver/catalog.json` | bilingual identity, ambiguity, unknown input, timeout/partial, cache, context ranking and CLI compatibility tested |
| 3 — aliases | Complete | `gamepulse/aliases.py`, `docs/alias_validation.md` | official, localized, abbreviation, nickname, misspelling, duplicate, provenance and ambiguity rules tested |
| 4 — query builder | Complete | `gamepulse/query_builder.py`, `config/query_templates.yaml`, `scripts/gamepulse.py` | bilingual/source-specific plans, disambiguation, intent separation, Steam identity, deduplication, caps and CLI preview tested |
| 5 — Fact Layer | Complete | `gamepulse/facts.py`, `gamepulse/foundation.py`, `tests/fixtures/facts/*`, `scripts/validate_foundation_examples.py` | official/store normalization, minimum vs recommended, missing cross-save, conflicts, platform/territory scope, separate store and fact-only bundle tested |

Each issue was committed separately in dependency order before the live end-to-end hardening pass.

## Test results

- Full repository suite: **57/57 passing**.
- Live-example validator: **3/3 passing**.
- Python compilation: passing.
- JSON Schema regeneration: deterministic and clean.
- Diff whitespace check: passing.
- Game-specific hard-code scan across `gamepulse/`, `scripts/` and `config/`: no tested game names or app IDs found.
- Existing pre-Issue tests remain passing.

Failure-path coverage includes an unknown title, an ambiguous same-name game, a provider timeout, a partial provider result and an alias-provider timeout. The pipeline returns typed status/warnings and does not fabricate aliases, plans or facts.

## Live end-to-end results

The examples below were collected through `scripts/gamepulse.py foundation`; no resolver or fact fixture was injected.

| Input | Canonical identity and titles | Alias result | Query plans | Fact result |
| --- | --- | --- | ---: | --- |
| `无限暖暖` | `game_wikidata_q126199544`; Wikidata `Q126199544`; Steam `3164330`; `无限暖暖` / `Infinity Nikki` | both official/localized titles validated and standalone-safe | 32 across `zh-CN` and `en` | 11 facts, 1 Steam evidence record |
| `PUBG: BATTLEGROUNDS` | `game_steam_578080`; Steam `578080` | `PUBG` observed through Steam search; `medium`, `scoped_only`, not standalone-safe | 44 across `zh-CN` and `en` | 10 facts, 1 Steam evidence record |
| `Counter-Strike 2` | `game_steam_730`; Steam `730` | `CS2` observed through Steam search; `high`, `scoped_only`, not standalone-safe | 44 across `zh-CN` and `en` | 10 facts, 1 Steam evidence record |

Evidence checks:

- Each resolved identity contains resolver evidence IDs.
- Each non-official alias contains an evidence ID, source URL and captured top-search-result excerpt.
- `PUBG` and `CS2` were proposed generically from their titles and retained only after Steam search returned the same app ID.
- No high-ambiguity alias appears in a plan without disambiguators.
- Every `FactRecord.source_evidence_id` resolves to a Fact Layer `EvidenceItem` with source URL, checksum, authority and retrieval time.
- Fact evidence kinds remain `fact_source`/official; player reviews and comments are not loaded into the Fact Layer.

Live outputs:

- `examples/foundation/infinity-nikki.json`
- `examples/foundation/pubg-battlegrounds.json`
- `examples/foundation/counter-strike-2.json`

## Current failure behaviour

These are handled outcomes rather than silent failures:

- Ambiguous input returns `needs_choice` with multiple candidates and no selected game.
- Unknown input returns `unresolved`; aliases, query plans and facts remain empty.
- Provider timeout is retained as a typed provider failure. Another provider may still produce a `partial` resolution.
- Alias-provider failure falls back to evidenced official/localized titles and records a stage warning.
- Missing Steam identity returns an empty Fact bundle with an explicit warning.
- Missing cross-save, current-version or patch data creates no affirmative fact.
- Conflicting facts remain as separate `conflicting` records.

## Known limitations

- Steam is the only live Fact adapter in this checkpoint. The official structured adapter is executable but expects already-authorised structured metadata; it does not scrape arbitrary official sites.
- Steam-search alias discovery currently validates abbreviations discoverable in the platform index. Unindexed community nicknames are not auto-promoted. They require independent evidence observations; co-occurrence-only terms remain pending.
- Query plans for official web, Reddit and Bilibili are generated but not executed by the new architecture until Issue 6 adapter migration.
- System requirements remain source text except for extracted storage amounts; CPU/GPU/RAM are not yet normalized into a hardware ontology.
- Resolver provider availability varies. Cached responses and Steam fallback reduce impact, but a non-Steam game may remain unresolved when Wikidata is unavailable.
- Resolver cache expiry and immutable raw snapshots for alias-search evidence are not yet implemented.
- The existing legacy collection/report pipeline remains separate from this foundation slice until Issue 6.

## Real implementation vs interface/spec

### Real and executable

- Pydantic contracts and checked-in JSON Schemas.
- Legacy voice-row compatibility conversion.
- Wikidata/Steam candidate resolution, ranking, cache and typed failure states.
- Official/localized aliases and deterministic alias validation.
- Steam-index-backed abbreviation observations with evidence excerpts.
- English/Chinese source-aware Query Plans with safety rules and caps.
- Steam Fact retrieval and official structured-metadata normalization.
- Fact conflict reconciliation, separate JSONL Fact store and `Can I run it?` fact-only bundle.
- `plan` and `foundation` CLI paths.

### Interface/spec only at this checkpoint

- Issue 6 adapter migration and execution of new Query Plans.
- New relevance/corpus/evidence-store pipeline for public UGC.
- Cross-game UGC taxonomy and evidence-linked insights.
- Player, Creator, Analyst and Compare mode renderers.
- Patch Intelligence and authorised private-data ingestion.
- API server, dashboard and vector database (explicitly out of scope).

## Release judgment

**Yes, the Issue 1–5 foundation is a genuinely runnable vertical slice for its stated scope.** It is not yet the complete PlayerVoice product: it can reliably perform name-to-identity-to-safe-query-to-official-fact work, while public player-voice retrieval and analysis remain behind the Issue 6 boundary.
