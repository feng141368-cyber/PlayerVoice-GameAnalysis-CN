# Evidence-linked insights (Issue 10)

Issue 10 completes the core PlayerVoice path from a resolved game name to a
bounded, source-traceable finding. It does not implement Player, Creator,
Analyst, or Compare Mode APIs.

## Runtime path

`gamepulse.voice_slice.run_voice_slice` composes the existing layers in this
order:

1. resolve the game and validate aliases;
2. build multilingual, platform-specific query plans;
3. collect community evidence through Issue 6 adapters and Fact Layer records
   through the existing official path;
4. score relevance and keep only `relevant` community evidence in the default
   analysis corpus;
5. deduplicate source items while retaining every query link;
6. write versioned annotations to `annotations.jsonl`;
7. generate evidence-bounded insights and render a traceback report.

The CLI entry point is:

```bash
python scripts/gamepulse.py voice-slice \
  --game "无限暖暖" \
  --output examples/e2e/infinity-nikki
```

An already validated Issue 1–5 result may be supplied with `--foundation` for
an explicit offline fallback. This reuses known identity/fact evidence; it does
not fabricate community content.

## Insight contract

The engine can emit bounded `praise`, `complaint`, `controversy`, `difference`,
`research_gap`, and `opportunity` records. Every record contains at least one
evidence link, sample scope, confidence, and uncertainty. A controversy needs
distinguishable positive and negative evidence; mixed-only evidence is
downgraded to an open research question.

Opportunities explicitly identify whether they came from a player's stated
request or an inferred need. Missing support produces no insight. Facts remain
in `FactRecord` objects and appear in a separate report section from player
evidence.

## Priority semantics

Complaint and opportunity priorities expose four inspectable components:

- observed evidence volume;
- negative share in the collected sample;
- recent-versus-prior momentum when enough dated evidence exists;
- breadth across sources that were actually collected or partially collected.

Unavailable and disabled sources are excluded from the breadth denominator.
Every priority carries this disclaimer:

> Triage decision support from observed evidence volume, negative share,
> momentum, and source breadth; not a causal effect or population-prevalence
> estimate.

## Coverage and integrity

`CoverageReport` records source status, attempted queries, raw retrieved and
relevance counts, duplicates, date range, languages, exclusions, and failure
reasons. Fact evidence retains its real platform source for provenance but is
reported under the separate `official` coverage bucket so community counts are
not inflated.

Before a Markdown report is written, integrity validation checks that every
Insight and Fact evidence ID resolves in the Evidence Store and that the
reported relevant-corpus size matches the store. The final traceback table
resolves each evidence ID to stored original text and its source URL/reference.

## Deliberate limits

- Rules are transparent baselines, not an opaque semantic classifier.
- Public community samples are self-selected and are not population estimates.
- Momentum is omitted when the sample lacks enough dated evidence.
- Exact content/source deduplication is automatic; semantic near-duplicates are
  only marked when reliably identifiable and are not automatically merged.
- Reddit requires OAuth credentials. Bilibili public endpoints may return
  partial or rate-limited results. These states remain visible rather than being
  converted into zero feedback.
- Issue 11 Mode routing, dashboards, APIs, vector search, recommendations, and
  causal patch analysis remain unimplemented.
