from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def write_report(result: dict[str, Any], output_dir: Path) -> Path:
    game = result["game"]
    topics = result["topic_summary"]
    sources = result["source_summary"]
    lines = [
        f"# {game}: Voice-of-Player Report",
        "",
        f"**Coverage:** {result['records']:,} real public records across {result['sources']} collected source(s).",
        f"**Trend anchor:** {result['anchor_date']} · **comparison window:** {result['window_days']} days.",
        "",
        "## Executive summary",
        "",
    ]
    top = topics[topics.topic != "Other"].head(3)
    if not top.empty:
        summary = "; ".join(
            f"{row.topic} ({row.priority}, {row.records} records, {_pct(row.negative_share)} negative proxy)"
            for row in top.itertuples(index=False)
        )
        lines.append(f"The highest-priority detected themes are {summary}. Priority is a triage signal based on volume, negativity, momentum, and cross-source breadth; it is not proof of product impact.")
    lines += ["", "## Source coverage", "", "| Source | Records | Earliest | Latest | Negative proxy | Engagement |", "| --- | ---: | --- | --- | ---: | ---: |"]
    for row in sources.itertuples(index=False):
        lines.append(f"| {row.source} | {row.records:,} | {str(row.earliest)[:10]} | {str(row.latest)[:10]} | {_pct(row.negative_share)} | {int(row.engagement):,} |")
    lines += ["", "## Issue priority", "", "| Priority | Topic | Records | Share | Negative proxy | Momentum | Sources |", "| --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for row in topics.itertuples(index=False):
        lines.append(f"| {row.priority} | {row.topic} | {row.records:,} | {_pct(row.share)} | {_pct(row.negative_share)} | {row.momentum:.2f}× | {row.sources} |")
    lines += ["", "## Evidence excerpts", ""]
    for topic, excerpts in result["excerpts"].items():
        if not excerpts:
            continue
        lines += [f"### {topic}", ""]
        for item in excerpts:
            text = item["text"].replace("\n", " ")
            source = item["source"]
            if item.get("url"):
                lines.append(f"- **{source}:** “{text}” ([source]({item['url']}))")
            else:
                lines.append(f"- **{source}:** “{text}”")
        lines.append("")
    lines += [
        "## Recommended next actions", "",
        "1. Review the highest-priority theme against a human-coded sample before making a product decision.",
        "2. Separate platform-specific issues from themes that converge across store, social, and community sources.",
        "3. Track topic share and negative proxy over repeated collection windows; investigate material changes rather than one-off volume.",
        "4. Link confirmed player-voice themes to first-party telemetry or experiments before claiming behavioural or revenue impact.",
        "", "## Limitations", "",
        "- Store recommendation status is a source-native signal; Reddit, YouTube, Bilibili, and imported-community sentiment uses a transparent lexicon proxy.",
        "- Search ranking and API availability create sampling bias, and deleted or private content is not observed.",
        "- A post or comment can contain multiple topics, while the baseline classifier assigns one primary topic.",
        "- Public discussion cannot be assumed to represent the full player population.",
        "- Platform access status is recorded in `data/raw/latest_manifest.json`; unavailable sources must not be described as collected.",
        "",
    ]
    path = output_dir / "voice_of_player_report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    json_path = output_dir / "analysis_summary.json"
    json_path.write_text(
        json.dumps(
            {"game": game, "records": result["records"], "sources": result["sources"],
             "anchor_date": result["anchor_date"], "window_days": result["window_days"],
             "topics": result["topic_summary"].to_dict("records"), "excerpts": result["excerpts"]},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    return path


def create_chart(result: dict[str, Any], output_dir: Path) -> Path:
    topics = result["topic_summary"][result["topic_summary"].topic != "Other"].head(8).sort_values("priority_score")
    fig, ax = plt.subplots(figsize=(10, 5.4))
    colors = {"P0": "#B23A48", "P1": "#D17B49", "P2": "#6C63B5", "P3": "#AAB4C4"}
    ax.barh(topics.topic, topics.priority_score, color=[colors[p] for p in topics.priority])
    for y, row in enumerate(topics.itertuples(index=False)):
        ax.text(row.priority_score + 0.12, y, f"{row.priority} · {row.records} records", va="center", fontsize=9)
    ax.set_xlim(0, 12.8)
    ax.set_xlabel("Priority score (0–12)")
    ax.set_title(f"{result['game']}: cross-source issue priorities", loc="left", fontweight="bold", fontsize=14)
    ax.grid(axis="x", alpha=0.2)
    ax.spines[["top", "right"]].set_visible(False)
    fig.text(0.125, 0.01, "Real public-source sample. Scores support triage, not causal claims.", fontsize=8, color="#555")
    fig.tight_layout(rect=[0, 0.04, 1, 1])
    path = output_dir / "issue_priorities.png"
    fig.savefig(path, dpi=170, bbox_inches="tight")
    plt.close(fig)
    return path
