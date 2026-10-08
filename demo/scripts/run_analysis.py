#!/usr/bin/env python3
"""Execute SQL metrics and produce an evidence-grounded product report."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import pandas as pd


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def priority(total: int) -> str:
    if total >= 10:
        return "P0"
    if total >= 7:
        return "P1"
    if total >= 4:
        return "P2"
    return "P3"


def run(database: Path, sql_dir: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        metrics = {}
        for name in ["retention", "monetization", "engagement", "segmentation"]:
            metrics[name] = pd.read_sql_query((sql_dir / f"{name}.sql").read_text(), connection)
            metrics[name].to_csv(output_dir / f"{name}.csv", index=False)

        internal = pd.read_sql_query("SELECT * FROM feedback", connection)
        market = pd.read_sql_query("SELECT * FROM market_reviews", connection)
        players = pd.read_sql_query("SELECT COUNT(*) AS n FROM players", connection).iloc[0]["n"]
        sessions = pd.read_sql_query("SELECT COUNT(*) AS n FROM sessions", connection).iloc[0]["n"]
        runway = pd.read_sql_query(
            """
            WITH participants AS (
              SELECT DISTINCT player_id FROM gameplay_events WHERE event_name='celestial_runway_joined'
            ), outfit_buyers AS (
              SELECT DISTINCT player_id FROM payments WHERE product_type='outfit'
            )
            SELECT COUNT(*) AS participants,
                   SUM(CASE WHEN b.player_id IS NOT NULL THEN 1 ELSE 0 END) AS outfit_buyers
            FROM participants p LEFT JOIN outfit_buyers b USING(player_id)
            """,
            connection,
        ).iloc[0]

    retention = metrics["retention"]
    segments = metrics["segmentation"]
    engagement = metrics["engagement"]

    def segment_value(frame: pd.DataFrame, **filters):
        result = frame
        for column, value in filters.items():
            result = result[result[column] == value]
        if len(result) != 1:
            raise ValueError(f"Expected one row for {filters}, found {len(result)}")
        return result.iloc[0]

    android_pre = segment_value(segments, patch_version=1.2, platform="Android")
    android_post = segment_value(segments, patch_version=1.3, platform="Android")
    android_ret_pre = segment_value(retention, cohort_period="pre_1.3", platform="Android")
    android_ret_post = segment_value(retention, cohort_period="post_1.3", platform="Android")
    companion_no = engagement[(engagement.companion_adopter == 0)].groupby("companion_adopter").agg(
        players=("players", "sum"), d30_players=("d30_players", "sum")
    ).iloc[0]
    companion_yes = engagement[(engagement.companion_adopter == 1)].groupby("companion_adopter").agg(
        players=("players", "sum"), d30_players=("d30_players", "sum")
    ).iloc[0]
    companion_no_rate = companion_no.d30_players / companion_no.players
    companion_yes_rate = companion_yes.d30_players / companion_yes.players

    internal_summary = (
        internal.assign(negative=internal.rating <= 2)
        .groupby(["patch_version", "topic"], as_index=False)
        .agg(feedback_count=("feedback_id", "count"), negative_count=("negative", "sum"), avg_rating=("rating", "mean"))
    )
    internal_summary["negative_share"] = internal_summary.negative_count / internal_summary.feedback_count
    internal_summary.to_csv(output_dir / "feedback_topics.csv", index=False)
    market_summary = (
        market.groupby(["app_name", "topic"], as_index=False)
        .agg(review_count=("market_review_id", "count"), positive_share=("voted_up", "mean"))
    )
    market_summary.to_csv(output_dir / "market_review_topics.csv", index=False)

    post_feedback = internal[internal.patch_version == 1.3]
    perf_count = int((post_feedback.topic == "Performance").sum())
    perf_share = perf_count / len(post_feedback) if len(post_feedback) else 0
    outfit_conversion = runway.outfit_buyers / runway.participants if runway.participants else 0

    priorities = [
        {"issue": "Mobile performance after patch 1.3", "frequency": 3, "severity": 3, "affected_segment": 3,
         "behavioural_signal": 3},
        {"issue": "Runway event monetization friction", "frequency": 2, "severity": 2, "affected_segment": 2,
         "behavioural_signal": 2},
        {"issue": "Companion depth and repeat dialogue", "frequency": 2, "severity": 1, "affected_segment": 2,
         "behavioural_signal": 2},
    ]
    for item in priorities:
        item["score"] = sum(item[key] for key in ["frequency", "severity", "affected_segment", "behavioural_signal"])
        item["priority"] = priority(item["score"])

    facts = {
        "android_crash_rate_pre": float(android_pre.crash_rate),
        "android_crash_rate_post": float(android_post.crash_rate),
        "android_d7_pre": float(android_ret_pre.d7_retention),
        "android_d7_post": float(android_ret_post.d7_retention),
        "post_patch_performance_feedback_share": perf_share,
        "runway_participants": int(runway.participants),
        "runway_outfit_buyers": int(runway.outfit_buyers),
        "runway_outfit_conversion": outfit_conversion,
        "companion_adopter_d30": companion_yes_rate,
        "non_adopter_d30": companion_no_rate,
    }

    recommendations = [
        {
            "priority": "P0",
            "issue": "Mobile performance after patch 1.3",
            "evidence": [
                f"Android session crash rate changed from {pct(facts['android_crash_rate_pre'])} in patch 1.2 to {pct(facts['android_crash_rate_post'])} in patch 1.3.",
                f"Android D7 cohort retention changed from {pct(facts['android_d7_pre'])} before patch 1.3 to {pct(facts['android_d7_post'])} after it.",
                f"Performance represented {pct(perf_share)} of first-party feedback recorded in patch 1.3 ({perf_count}/{len(post_feedback)} rows).",
            ],
            "interpretation": "The aligned timing and segment concentration justify urgent diagnosis, but the observational data do not establish that crashes alone explain the retention difference.",
            "action": "Instrument crash signatures by Android device tier, hotfix the two largest signatures, and run a staged rollout with a holdout where operationally safe.",
            "metric": "Android crash-free sessions, D1/D7 retention by device tier, and support-ticket rate.",
            "confidence": "high for the performance problem; medium for its retention contribution",
        },
        {
            "priority": "P1",
            "issue": "Runway event monetization friction",
            "evidence": [
                f"The Celestial Runway event had {int(runway.participants)} participants; {int(runway.outfit_buyers)} bought an outfit ({pct(outfit_conversion)} participant conversion).",
                "First-party feedback contains explicit price, pity, currency, and paywall language; topic counts are available in outputs/feedback_topics.csv.",
            ],
            "interpretation": "Participation indicates interest, while the purchase funnel and pricing feedback support testing value presentation and entry price rather than assuming weak demand.",
            "action": "A/B test an event bundle with a lower-priced first purchase and a transparent cosmetic-only reward path.",
            "metric": "Participant-to-outfit conversion, net revenue per participant, refund rate, and event completion.",
            "confidence": "medium",
        },
        {
            "priority": "P1",
            "issue": "Companion system retention opportunity",
            "evidence": [
                f"D30 retention was {pct(companion_yes_rate)} among companion adopters and {pct(companion_no_rate)} among non-adopters.",
                "Companion feedback mixes positive attachment language with complaints about repeated dialogue and progression caps.",
            ],
            "interpretation": "Companion engagement is a promising retention marker, but self-selection is likely because players already inclined toward relationship content adopt it more often.",
            "action": "Randomize an earlier companion-system introduction for eligible new players and add dialogue-variety content to the treatment experience.",
            "metric": "Companion activation, D7/D30 retention, dialogue repetition reports, and session frequency.",
            "confidence": "medium-low until experimentally tested",
        },
    ]

    report = {
        "project": "GamePulse",
        "product": "Veloura: Threads of Aster (fictional)",
        "data_scope": {
            "players": int(players), "sessions": int(sessions), "first_party_feedback": int(len(internal)),
            "market_reviews": int(len(market)), "observation_end": "2026-05-31",
            "data_note": "Behavioural and first-party feedback data are synthetic; market reviews are public cross-product context.",
        },
        "facts": facts,
        "priority_matrix": priorities,
        "recommendations": recommendations,
        "metrics_to_monitor": [
            "D1/D7/D30 retention by signup cohort and platform",
            "Crash-free session rate by platform and device tier",
            "Runway participant-to-outfit conversion and revenue per participant",
            "Companion activation and retention by randomized exposure",
        ],
        "limitations": [
            "The focal product telemetry and first-party feedback are deterministic synthetic data created for portfolio demonstration.",
            "Public Steam reviews come from adjacent products and are market context, not evidence of Veloura user behaviour.",
            "Retention comparisons are observational and may reflect acquisition mix, seasonality, or unmeasured differences.",
            "Rule-based topic labels are transparent but can miss sarcasm, mixed topics, and domain-specific phrasing.",
            "Companion adoption is self-selected, so its retention association should be tested experimentally.",
        ],
    }
    (output_dir / "product_intelligence.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (output_dir / "product_intelligence.md").write_text(render_markdown(report), encoding="utf-8")
    return report


def render_markdown(report: dict) -> str:
    scope = report["data_scope"]
    lines = [
        "# GamePulse Product Intelligence Report",
        "",
        f"**Product:** {report['product']}",
        "",
        "## Executive summary",
        "",
        "The strongest product signal is a post-update Android performance problem aligned with weaker cohort retention and increased performance feedback. The fashion event attracts participation but converts relatively few participants to direct outfit purchases. Companion adoption is associated with stronger D30 retention, but self-selection prevents a causal conclusion.",
        "",
        "## Data scope and quality",
        "",
        f"- {scope['players']:,} synthetic players and {scope['sessions']:,} synthetic sessions through {scope['observation_end']}.",
        f"- {scope['first_party_feedback']:,} synthetic first-party feedback rows.",
        f"- {scope['market_reviews']:,} privacy-minimized public Steam reviews used only as cross-product market context.",
        "",
        "## Priority matrix",
        "",
        "| Priority | Issue | Score | Evidence use |",
        "| --- | --- | ---: | --- |",
    ]
    for item in report["priority_matrix"]:
        lines.append(f"| {item['priority']} | {item['issue']} | {item['score']}/12 | Investigation priority, not causal proof |")
    lines += ["", "## Recommendations", ""]
    for recommendation in report["recommendations"]:
        lines += [
            f"### {recommendation['priority']} — {recommendation['issue']}", "", "**Observed evidence**", ""
        ]
        lines += [f"- {evidence}" for evidence in recommendation["evidence"]]
        lines += [
            "", f"**Interpretation:** {recommendation['interpretation']}", "",
            f"**Action:** {recommendation['action']}", "",
            f"**Metric:** {recommendation['metric']}", "",
            f"**Confidence:** {recommendation['confidence']}", "",
        ]
    lines += ["## Limitations", ""] + [f"- {item}" for item in report["limitations"]]
    lines += ["", "## Detailed outputs", "", "See the CSV files in `outputs/` for retention, monetization, engagement, segmentation, and feedback-topic tables.", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=Path("outputs/gamepulse.db"))
    parser.add_argument("--sql-dir", type=Path, default=Path("sql"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    args = parser.parse_args()
    report = run(args.database, args.sql_dir, args.output_dir)
    print(f"Wrote report with {len(report['recommendations'])} recommendations")


if __name__ == "__main__":
    main()
