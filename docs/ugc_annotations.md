# UGC annotation baseline

Issue 9 replaces the legacy single-label classifier for the new PlayerVoice
corpus with a transparent, versioned, multi-label annotator. The old report
pipeline remains backward compatible and separate.

## Taxonomy activation

`config/taxonomy.yaml` is loaded and validated for unique IDs, required English
and Chinese labels, valid parents, and an explicit unknown topic. Core topic IDs
are always available. Genre extensions activate only when `GameEntity.genres`
matches their declared triggers; extension topics supplement rather than
replace core topics.

The initial rules emphasize the stable cross-game core: performance,
bugs/stability, gameplay, combat, exploration, story, characters, progression,
grind, controls, UI/UX, graphics, audio, monetisation/gacha, PvP/social,
endgame, and patch reaction. Gacha, MMO, simulation, and fashion extension
interfaces are supported without claiming equal rule depth for every node.

## Separated outputs

For each evidence item, the annotator creates a new `AnalysisAnnotation` and
does not mutate source evidence. It records:

- one primary and optional secondary topics;
- inferred sentiment (`positive`, `negative`, `mixed`, `neutral`, `unknown`);
- explicit or tightly bounded pain points;
- separately labelled inferred needs;
- only explicitly stated feature requests;
- behaviour signals only when explicit text cues exist.

Source-native Steam recommendation/rating remains on `EvidenceItem` and is not
overwritten when lexical sentiment differs. Behaviour signals are labelled in
the method metadata as expressed intent, not observed behaviour. Missing
support produces empty lists rather than invented requests or needs.

Every annotation stores taxonomy version, taxonomy config hash, method version,
inspectable topic scores, sentiment method/terms, confidence, and human-review
status. `other_unclassified` is explicitly not priority-eligible.
