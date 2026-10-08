# Corpus & Taxonomy Quality Gate (Issue 10.5)

Date: 2026-10-03  
Scope: every `other_unclassified` annotation in the checked-in live Infinity
Nikki, PUBG: BATTLEGROUNDS, and Counter-Strike 2 corpora (39/56 relevant
evidence items before the gate).

## Decision rule

The purpose of this gate is meaningful coverage, not a zero-unclassified
target. A topic was added or a rule expanded only when the evidence expressed
a reliable, reusable product theme. Generic praise, unclear slang, reactions,
and genre detail without a safely activated extension remain
`other_unclassified`.

## Root-cause totals

| Root cause | Count | Action |
| --- | ---: | --- |
| Missing taxonomy category | 4 | Added one reusable core topic: `fair_play_integrity` |
| Rule / classifier coverage gap | 5 | Added narrow bilingual variants for existing topics |
| Insufficient context | 18 | Remain unclassified |
| Non-product / non-gameplay conversation | 1 | Remain unclassified |
| Noise | 8 | Remain unclassified |
| Potential genre-specific topic | 3 | Remain unclassified pending safe extension activation |
| **Total reviewed** | **39** | **9 newly classified; 30 intentionally unclassified** |

## Full evidence review

### Infinity Nikki — 13 reviewed

| Evidence | Short excerpt | Root cause | Decision after gate |
| --- | --- | --- | --- |
| `ev_02da4c0963ab311214e1` | “still enjoying the game” | Insufficient context | Keep unclassified: engagement statement without a product dimension |
| `ev_0fb6696dee2499b24684` | “money for the gachas” | Rule gap | `gacha`; plural English form added |
| `ev_3595b6d5408b1689ed2b` | `WO XI HUAN CA DNVISE` | Noise | Keep unclassified: unreliable transliteration |
| `ev_3bc0491398dd34f16641` | “i am infinity nikki” | Non-product conversation | Keep unclassified |
| `ev_9f2811b35da6b6ce7b83` | `..` | Noise | Keep unclassified |
| `ev_a0e07254b48931a9a78c` | “豪玩” | Insufficient context | Keep unclassified: generic praise/slang, no topic |
| `ev_adfadfca748f9da41a6c` | community in-joke under an攻略 video | Noise | Keep unclassified |
| `ev_b3c11c7fa55e4a4df600` | “it won't play … freezes” | Rule gap | `bugs_stability`; inflected `freezes` added |
| `ev_b639d04f1b9f35bea61b` | “服装很精致…大世界与换装” | Potential genre topic | Keep unclassified pending fashion-customisation extension activation |
| `ev_be8baa5390535c10f991` | “7 outfit slots” | Potential genre topic | Keep unclassified pending `fashion.wardrobe` |
| `ev_d98217faa47bfe6b0ef3` | “outfits … cute” | Potential genre topic | Keep unclassified pending `fashion.wardrobe` |
| `ev_e46e4de12b5500517859` | “love it but its really big” | Insufficient context | Keep unclassified: “big” does not reliably establish storage/performance |
| `ev_e56c16619f4c9c19fbfa` | “Shroomtastic!” | Noise | Keep unclassified |

### PUBG: BATTLEGROUNDS — 18 reviewed

| Evidence | Short excerpt | Root cause | Decision after gate |
| --- | --- | --- | --- |
| `ev_01883a372fdec77a4c5a` | “全是职业选手” | Rule gap | `difficulty`; narrow skill-gap phrase added |
| `ev_04529a1e2fcd46bdf814` | unclear romanisation | Noise | Keep unclassified |
| `ev_20be927e0294398eb76c` | `666…` | Noise | Keep unclassified |
| `ev_227b24fade48c22f9655` | “好玩” | Insufficient context | Keep unclassified: sentiment is known, topic is not |
| `ev_2623045316461bffb5aa` | “垃圾箱子，圈钱第一名” | Rule gap | `monetisation`; strong “圈钱” cue added |
| `ev_2633dcaba231aeda6a90` | “GOOD” | Insufficient context | Keep unclassified |
| `ev_26b6cd199aca6893a165` | `ka` | Insufficient context | Keep unclassified: unsafe to assume “卡顿” |
| `ev_384b959c8e823e205d16` | `666` | Noise | Keep unclassified |
| `ev_4d09d01f7e517c1e98de` | “大逃杀经典之作” | Insufficient context | Keep unclassified: genre-level endorsement, no specific dimension |
| `ev_55d9d2a6369b7757f5a5` | server lag, anti-cheat, false detection | Missing category | `fair_play_integrity` primary; performance remains available where supported |
| `ev_5a6a74fd356c76f1640c` | “挂多的一批” | Missing category | `fair_play_integrity` |
| `ev_75f075da1f3b258bcad5` | cheating and bans affecting legitimate players | Missing category | `fair_play_integrity` |
| `ev_80a1a7132fad2687e5fe` | “好玩” | Insufficient context | Keep unclassified |
| `ev_9052a5f8d1778708308f` | “喜欢” | Insufficient context | Keep unclassified |
| `ev_90ba3a1949eb63aa9bbe` | “非常好玩有娱乐性” | Insufficient context | Keep unclassified |
| `ev_cdf14476e46b9ea4c72c` | “人机太多了” | Missing category | `fair_play_integrity` |
| `ev_e48c6137fe0de8a6b29a` | cannot pull desired item; “再也不充了” | Rule gap | `gacha` + `payment_withdrawal` expressed intent |
| `ev_f63a74f8afbca4051100` | “好玩” | Insufficient context | Keep unclassified |

### Counter-Strike 2 — 8 reviewed

| Evidence | Short excerpt | Root cause | Decision after gate |
| --- | --- | --- | --- |
| `ev_1677bfc8629c8dcd72c6` | “好玩” | Insufficient context | Keep unclassified |
| `ev_2f709f997cbdc9eebdea` | “非常好玩都给我来玩” | Insufficient context | Keep unclassified; recommendation intent has no reliable product topic |
| `ev_66530f0ac34486ba595c` | “很牛逼” | Insufficient context | Keep unclassified |
| `ev_88e260c23469244a562f` | `111` | Noise | Keep unclassified |
| `ev_8fdfbbeecedac92f12d9` | “好玩” | Insufficient context | Keep unclassified |
| `ev_b960397be96dd8d1aba3` | “好” | Insufficient context | Keep unclassified |
| `ev_c37c37071005a57a10a4` | “好” | Insufficient context | Keep unclassified |
| `ev_f74b5a0c988d870e87fb` | “牛逼” | Insufficient context | Keep unclassified |

## Changes accepted

### Core taxonomy

`fair_play_integrity` was added because four independent PUBG reviews express a
coherent product theme that did not fit existing `pvp`, `account_service`, or
`bugs_stability` definitions: cheating, anti-cheat effectiveness, bots, and
false-positive enforcement. It is reusable across competitive games and is not
specific to PUBG.

### Rule coverage

Narrow rules were added for:

- `gachas`, `抽不出来`, and `抽不到` → existing core `gacha`;
- `freezes` → existing `bugs_stability`;
- `全是职业选手` → existing `difficulty`;
- `圈钱` → existing `monetisation`;
- `再也不充` / `不充了` → `payment_withdrawal`, still explicitly labelled
  `expressed_intent_not_observed_behaviour`.

Generic `好玩`, `GOOD`, `牛逼`, numeric reactions, ambiguous `ka`, and generic
endorsements did not receive gameplay labels. This is the precision guard.

## Coverage before and after

| Game | Before unclassified | After unclassified | Meaningfully classified coverage before | After |
| --- | ---: | ---: | ---: | ---: |
| Infinity Nikki | 13/26 (50.0%) | 11/26 (42.3%) | 50.0% | 57.7% |
| PUBG: BATTLEGROUNDS | 18/20 (90.0%) | 11/20 (55.0%) | 10.0% | 45.0% |
| Counter-Strike 2 | 8/10 (80.0%) | 8/10 (80.0%) | 20.0% | 20.0% |
| **Combined** | **39/56 (69.6%)** | **30/56 (53.6%)** | **30.4%** | **46.4%** |

All nine newly classified items were manually rechecked against their original
text: 9/9 match the assigned topic. One already-classified PUBG performance
item also gained a correct `fair_play_integrity` secondary topic. No existing
topic was displaced, and the 30 weak-context/noise/genre-extension items remain
unclassified. This is a targeted audit, not a general benchmark.

## Precision and behaviour-language checks

- The prior 30-item relevance audit remains unchanged; Issue 10.5 modifies
  annotation only, not retrieval or relevance admission.
- Generic praise regression fixtures explicitly require `other_unclassified`.
- New fair-play rules use narrow multi-character phrases rather than the single
  character `挂`.
- `payment_withdrawal` is rendered as a player-stated/expressed signal. It does
  not assert that spending actually stopped.
- `churn_risk` continues to mean expressed churn intent. Mode renderers must use
  “player stated”, “expressed intent”, or “possible relevance”, never “player
  churned”.

## Deferred genre extensions

Three Infinity Nikki outfit/wardrobe items are credible fashion-customisation
evidence. They remain unclassified because the current resolved GameEntity does
not contain a safely validated fashion/dress-up tag, so the extension is not
activated. A future metadata-quality task may add evidenced genre/tag mapping;
the classifier must not activate an extension from the demo game's name or a
hard-coded ID.

## Gate conclusion

Taxonomy version `1.1.0` improves meaningful coverage by 16 percentage points
across the live corpus without forcing generic/noisy evidence into product
topics. The remaining `other_unclassified` rate is expected and useful: it
exposes information quality and genre-metadata gaps rather than hiding them.

## Post-gate precision hardening from Compare validation

Issue 14's larger competitive-shooter sample exposed a separate precision
problem: the bare token `FPS` can mean the first-person-shooter genre rather
than frame-rate performance. Seven sampled items such as “经典的 FPS 游戏” and
“没有 FPS 天赋” were initially counted as `performance`. The rule is now
context-sensitive: `FPS` requires a number or an explicit frame-rate modifier,
while direct cues such as `优化`, `掉帧`, `frame rate`, and `performance`
continue to classify normally. The annotator method version is
`transparent-rules-v1.1.1`; taxonomy IDs remain version `1.1.0` because no
taxonomy node changed.

After reannotation, 6/6 manually sampled remaining performance items described
actual optimisation/frame-rate issues, and 9/9 sampled fair-play items
described cheating, anti-cheat, false bans, or match-integrity problems. The
original three-game Issue 10.5 primary-topic coverage table above is unchanged.
New regression tests distinguish `FPS game` from `30 FPS` / `FPS drops`.
