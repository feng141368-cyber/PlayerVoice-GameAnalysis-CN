# Issue 14 Implementation Review — Compare Mode

## Status

Completed. Compare Mode accepts two to four precomputed Intelligence Core
snapshots and does not invoke resolution, retrieval, relevance, annotation, or
insight generation itself.

## Files changed

- `gamepulse/modes/compare.py`: comparison contracts, common taxonomy
  dimensions, Fact Layer dimensions, coverage/confidence gates, optional
  preference-aware output, and Markdown rendering.
- `gamepulse/modes/router.py`, `gamepulse/modes/__init__.py`,
  `scripts/gamepulse.py`: shared routing and CLI output.
- `tests/test_modes_compare.py`, `tests/test_modes_player.py`: Issue 14
  acceptance and routing regression tests.
- `gamepulse/intelligence.py`, `tests/test_intelligence.py`: precision fix for
  ambiguous bare `FPS` genre mentions exposed by the live comparison.
- `examples/modes/compare/technical-three-games/*`: required Infinity Nikki,
  PUBG, and CS2 technical comparison.
- `examples/e2e/compare-demo/*`,
  `examples/modes/compare/competitive-shooters/*`: live comparable-games demo
  for PUBG, CS2, and Apex Legends.

## Functionality

- Aligns games by shared taxonomy version and rejects duplicate identities or
  incompatible taxonomy snapshots.
- Shows raw topic evidence counts, within-corpus share, source and language
  distribution, sentiment positions, date coverage, confidence, Insight IDs,
  and original evidence IDs.
- Shows verified Fact Layer values for platform support, minimum requirements,
  storage, supported languages, and cross-play; missing facts stay partial or
  insufficient.
- Marks a dimension `insufficient_evidence` if any game has fewer than three
  relevant items. Source-mix, recency, or greater-than-4× sample imbalance
  produces `comparable_with_caution`.
- Applies the existing Player `PreferenceProfile` per game when supplied.
- Emits no winner, universal recommendation score, or neutral value for missing
  evidence.

## Tests

- Eight Compare-specific acceptance tests cover three-game alignment,
  normalisation and coverage, insufficiency, Fact Layer separation, no winner,
  preferences, evidence traceback, and invalid contexts.
- Two annotation edge-case tests distinguish `FPS game` from `30 FPS`, `FPS
  drops`, and other actual performance language.
- Final full regression: **149/149 passing**; prior Issue 1–10 and Mode tests
  remain green.

## Real validation

### Required technical group

Infinity Nikki (26 relevant items), PUBG (20), and CS2 (10) load through the
same core. All 11 community dimensions remain `insufficient_evidence`; this is
the correct outcome for three dissimilar games and sparse per-topic samples.
Fact dimensions remain comparable where official facts exist. No missing
dimension is ranked as average.

### Comparable product demo

| Game | Relevant corpus | Source coverage | Language |
| --- | ---: | --- | --- |
| PUBG: BATTLEGROUNDS | 99 | Steam 99; Bilibili partial; Reddit unavailable | zh-CN 99 |
| Counter-Strike 2 | 154 | Steam 153; Bilibili 1; Reddit unavailable | zh-CN 154 |
| Apex Legends | 105 | Steam 100; Bilibili 5; Reddit unavailable | zh-CN 105 |

`fair_play_integrity` is the one evidence-supported cross-game comparison:

| Game | Evidence | Corpus share | Confidence |
| --- | ---: | ---: | --- |
| PUBG | 5 | 5.1% | medium |
| CS2 | 3 | 1.9% | medium |
| Apex Legends | 15 | 14.3% | medium |

It is labelled `comparable_with_caution`, not a winner, because the evidence
counts differ by more than 4×. A 9-item manual sample (three per game) was 9/9
on-topic for cheating, anti-cheat, false bans, or match integrity.

Performance remains insufficient after the precision fix: 3 PUBG, 1 CS2, and
2 Apex items. A six-item manual sample of the remaining performance set was
6/6 on-topic. Seven prior bare-`FPS` false positives were removed rather than
retained to make the comparison look stronger.

## Known limitations and deferred work

- Coverage is a recent, self-selected public sample, not player-population
  prevalence or game quality.
- The demo is dominated by Chinese Steam reviews. Reddit was unavailable
  without OAuth credentials; Bilibili was partial for PUBG/CS2.
- Ten of eleven community dimensions remain insufficient in the comparable
  demo. Compare Mode reports that honestly.
- Genre extensions are preserved in coverage metadata but are not forced into
  cross-game core comparisons.
- Patch causality, private data, segmentation, a dashboard, and a winner score
  are not implemented. Work stops before Issue 15.
