# PlayerVoice Mode Layer Implementation Review

Date: 2026-10-03
Scope: Issue 10.5 and the current phase's ordered Issue 11–14 implementation.
Issue 15+ is not included.

## Executive conclusion

PlayerVoice is now a usable, evidence-bounded product prototype for a player,
creator, or public-corpus analyst. All four Modes consume the same saved
Intelligence Core; they do not run separate search, scraping, relevance,
taxonomy, or insight pipelines. Outputs are available as typed Python models,
JSON, Markdown, and CLI commands.

It is not yet a production product. Source breadth is limited, many dimensions
correctly remain insufficient, preferences use transparent rules rather than a
learned semantic parser, and there is no UI, private-data join, patch causal
analysis, or enterprise infrastructure.

## 1. Issue 10.5 — Corpus & Taxonomy Quality Gate

All 39 original `other_unclassified` items across Infinity Nikki, PUBG, and
CS2 were reviewed individually in `docs/taxonomy_gap_analysis.md`.

| Root cause | Count | Result |
| --- | ---: | --- |
| Missing taxonomy category | 4 | Added reusable core `fair_play_integrity` |
| Rule / classifier coverage gap | 5 | Narrow bilingual rule additions |
| Insufficient context | 18 | Kept unclassified |
| Non-product conversation | 1 | Kept unclassified |
| Noise | 8 | Kept unclassified |
| Potential genre-specific topic | 3 | Deferred to safe extension activation |

| Game | Unclassified before | After | Meaningful coverage before | After |
| --- | ---: | ---: | ---: | ---: |
| Infinity Nikki | 13/26 | 11/26 | 50.0% | 57.7% |
| PUBG | 18/20 | 11/20 | 10.0% | 45.0% |
| CS2 | 8/10 | 8/10 | 20.0% | 20.0% |
| **Combined** | **39/56** | **30/56** | **30.4%** | **46.4%** |

The nine newly classified items were 9/9 correct in manual review. Thirty
items remain deliberately unclassified. Later Compare validation found that
bare `FPS` could mean a game genre; annotator `transparent-rules-v1.1.1`
removed seven false positives from the larger shooter demo while preserving
numeric/degrading FPS evidence. This reduced coverage and improved precision.

Behaviour language remains strict: `churn_risk` renders as
`expressed_churn_intent`; public statements never become “player churned” or a
causal retention claim.

## 2. Issue status and implementation

| Issue | Status | Main files | Delivered capability |
| --- | --- | --- | --- |
| 10.5 | Completed | `config/taxonomy.yaml`, `gamepulse/intelligence.py`, `tests/test_intelligence.py`, taxonomy review | Audited unclassified evidence, targeted taxonomy/rule improvements, precision guards |
| 11 Player | Completed | `gamepulse/modes/contracts.py`, `core.py`, `player.py`, `router.py`, CLI and tests | Fact + Player Evidence research summary, preference profile, dimension-level fit |
| 12 Creator | Completed | `gamepulse/modes/creator.py`, router/CLI and tests | Research brief, evidence-backed controversy, research questions and gaps |
| 13 Analyst | Completed | `gamepulse/modes/analyst.py`, annotation fixes and tests | Observed → inferred → expressed-intent → hypothesis product-insight chain |
| 14 Compare | Completed | `gamepulse/modes/compare.py`, router/CLI and tests | 2–4 game taxonomy/fact comparison with coverage, confidence, preferences, and no winner |

Per-Issue reviews are in `docs/ISSUE_11_IMPLEMENTATION_REVIEW.md` through
`docs/ISSUE_14_IMPLEMENTATION_REVIEW.md`.

## 3. Automated tests and regression

| Checkpoint | Passing tests |
| --- | ---: |
| Approved pre-phase baseline | 112 |
| After Issue 10.5 | 116 |
| After Issue 11 | 123 |
| After Issue 12 | 130 |
| After Issue 13 | 140 |
| Final after Issue 14 and FPS precision fix | **149** |

Final command: `python -m unittest discover -s tests -v`
Result: **149 passed, 0 failed, 0 errors; no regression**.

## 4. Player Mode real example

Input:

> 我每天大概只能玩一个小时。我喜欢探索、剧情和角色塑造。我不喜欢重
> PvP，也不喜欢每天必须上线做很多任务。比较在乎画面和音乐。

The parsed profile records 60 minutes/day; exploration, story, characters,
graphics, and audio as important; and PvP/daily commitment as avoidances.

For Infinity Nikki, the report separates verified Steam Fact Layer data
(identity, developer/publisher, release, Windows requirements, storage, and
cross-play) from public player evidence. Fit output is:

- Likely match: story (5 linked items), graphics (1), audio (1).
- Possible friction: none supported by this sample.
- Uncertain: exploration, characters, PvP, daily commitment, available-time
  fit, and controls.

The system does not turn missing PvP/daily evidence into a match and does not
say “buy this game.” Ten referenced evidence records resolve to original source
URLs/references.

## 5. Creator Research Brief real example

Infinity Nikki produces six praise claims, two complaint claims, three
research questions, one explicit taxonomy research gap, and one supported
story controversy. The controversy requires three positive and two negative
Steam evidence items with disjoint IDs; its output states that the sample
shows disagreement but does not establish player segments or population
polarisation.

Platform/language difference is explicitly insufficient because the sample
does not provide comparable multi-source breadth. The questions are labelled
`research_question` and `not_an_established_finding=true`.

## 6. Analyst Mode real example

Eight Infinity Nikki evidence chains cover story complaints, freeze/crash
reports, a gacha value concern, and one genuine “能不能一键跳过” request. Each
chain labels its epistemic status:

- raw player statement and explicit request: `observed`;
- topic, pain point, need, and derived opportunity: `inferred`;
- churn/bug/recommendation language: `expressed_intent`;
- possible satisfaction/retention/business relevance: `hypothesis`.

The report states `observed_behaviour_data_available=false`. Priority is a
transparent triage signal with a non-causal disclaimer, not a business-impact
estimate. All eight referenced items resolve to their original sources.

## 7. Compare Mode real examples

The required Infinity Nikki/PUBG/CS2 technical test loads 26/20/10 relevant
items through taxonomy `1.1.0`. All 11 community dimensions are insufficient;
official Fact dimensions remain visible. This proves that heterogeneous games
and missing evidence do not produce a false ranking.

The comparable shooter demo uses real live outputs:

| Game | Relevant corpus | Sources | Date coverage |
| --- | ---: | --- | --- |
| PUBG | 99 | Steam 99 | 2026-09-30 → 2026-10-03 |
| CS2 | 154 | Steam 153, Bilibili 1 | 2026-08-19 → 2026-10-03 |
| Apex Legends | 105 | Steam 100, Bilibili 5 | 2019-02-15 → 2026-10-03 |

`fair_play_integrity` is `comparable_with_caution`: PUBG 5 (5.1%), CS2 3
(1.9%), Apex 15 (14.3%). The output blocks a winner because sample counts
differ by more than 4×. Performance and the other ten dimensions remain
insufficient after false-positive removal. Thirty-four linked references in
the Compare response resolve to original source URLs/references.

## 8. Evidence traceability

The shared router walks each Mode payload, collects every linked evidence ID,
and resolves it through the same local Evidence Store. Unresolved IDs fail the
request. Fact claims additionally require both Fact IDs and source evidence
IDs; Player Evidence claims require both Insight IDs and evidence IDs.

Traceback is therefore executable, not a display convention:

`Mode claim → Insight/Fact ID → Evidence ID → original source URL/reference`.

## 9. Unsupported and insufficient-evidence handling

- Player controls, PvP, daily commitment, and time fit remain uncertain when
  evidence is missing.
- Creator Mode returns “No well-supported controversy detected” for weak cases
  and refuses unsupported platform/language differences.
- Analyst Mode exposes the lack of authorised behavioural/retention data and
  labels business relevance as hypothesis.
- Compare Mode requires at least three relevant items per game/dimension and
  displays source mix, language, recency, raw count, corpus share, and
  confidence before allowing comparison.
- Reddit remains `unavailable` without OAuth credentials. Bilibili partial/412
  outcomes remain visible rather than being treated as negative evidence.

## 10. Implemented, partial, and interface-only boundary

| Capability | State |
| --- | --- |
| Resolver → alias → query → Fact → retrieval → relevance → deduplicated corpus → annotation → Insight | Implemented and live-tested |
| Shared Player / Creator / public Analyst / Compare renderers | Implemented and CLI-runnable |
| Steam collection | Implemented and live-tested |
| Bilibili collection | Implemented but operationally partial on some runs |
| Reddit collection | Implemented adapter; unavailable in this validation without credentials |
| Transparent bilingual preference/taxonomy rules | Implemented baseline; vocabulary coverage is limited |
| Genre-specific taxonomy extensions | Schema/rules exist; activation depends on validated genre metadata |
| Private Data Ingestion | Interface-only and explicitly rejected by current Mode requests |
| Patch Intelligence, causal analysis, segmentation, dashboard/API server, vector database, enterprise auth/storage | Not implemented; Issue 15+ |

## 11. Shared Intelligence Core check

`load_core_snapshot()` loads the same `GameEntity`, Fact records, Evidence
Store, annotations, and Insight bundle for every Mode. `route_mode()` only
selects a presentation/reasoning renderer. Mode modules contain no source
adapter, resolver, relevance, corpus, or taxonomy execution. Tests verify that
all linked Mode evidence resolves against the supplied snapshots.

## Final answer

Yes—with explicit MVP limits. PlayerVoice has progressed from a Game
Intelligence pipeline into an actual product prototype that a player, Creator,
or analyst can run and inspect. Its strongest product property is not breadth:
it is the refusal to hide missing evidence, manufacture controversy, claim
observed churn, or rank incomparable games. Production readiness still needs
broader licensed/credentialed sources, stronger semantic coverage, product UI,
and later Issue 15+ work.
