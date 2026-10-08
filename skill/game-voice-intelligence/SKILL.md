---
name: game-voice-intelligence
description: Discover, collect, normalize, and analyze player feedback for a named game across storefronts, social video, forums, and authorized community exports. Use for cross-platform game review monitoring, issue discovery, player-voice research, competitor listening, or product-priority briefs; do not claim coverage for platforms that are unavailable or unauthorised.
---

# Game Voice Intelligence

Turn a game name into a traceable multi-source voice-of-player report.

## Workflow

1. Resolve the supplied game name into useful aliases before searching. Prefer the local discovery command; use web research when alias resolution is incomplete.
2. Read [platform-routing.md](references/platform-routing.md), select every requested and available source, and record unavailable sources rather than silently omitting them.
3. Collect through documented APIs, public endpoints with conservative limits, or user-authorized exports. Stop on authentication, CAPTCHA, rate-limit, or permission barriers; never bypass them.
4. Normalize every record to [normalized-schema.md](references/normalized-schema.md), retaining source, original URL, created time, collected time, and source-native engagement signals.
5. Deduplicate incrementally on stable source IDs. Keep raw snapshots and a run manifest.
6. Analyze topics, negative proxy, momentum, and cross-source breadth using [analysis-method.md](references/analysis-method.md).
7. Inspect representative source-linked excerpts before treating a machine-labelled theme as a product issue.
8. Return source coverage, findings, evidence links, actions, and limitations. State which sources were not collected and why.

## Analysis rules

- Never describe a configured source as collected unless the run manifest says `collected`.
- Do not treat search rank, likes, comment volume, or a sentiment proxy as representative prevalence.
- Keep source-native recommendation status distinct from lexicon- or model-derived sentiment.
- Do not merge different games merely because their names or aliases are similar.
- Exclude deleted, empty, private, or unauthorized content.
- Do not store credentials, profile names, or unnecessary personal identifiers in the repository.
- Treat an `Other` topic as a taxonomy-quality signal, not a product priority.
- Human-check linked excerpts before elevating a theme into a recommendation.

## Bundled execution

From the repository root, run:

```bash
python scripts/gamepulse.py run --game "Tower of Fantasy"
python skill/game-voice-intelligence/scripts/validate_run.py data/raw/latest_manifest.json reports/tower-of-fantasy/analysis_summary.json
```

Use `--config` for fixed aliases, limits, and credentials. Use `scripts/gamepulse.py import` for approved Weibo, Xiaohongshu, Douyin, Discord, or vendor exports.

## Output contract

Produce these sections:

1. Source coverage, status, date range, and sample count
2. Topic volume and source distribution
3. Negative proxy with its method by source
4. Recent-versus-prior momentum
5. Cross-source convergence
6. Representative linked excerpts
7. Product or research actions
8. Missing sources, sampling bias, and model limitations

Never infer first-party behavioural or revenue impact from public discussion alone. Recommend telemetry analysis or experiments when impact needs confirmation.
