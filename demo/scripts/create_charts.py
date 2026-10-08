#!/usr/bin/env python3
"""Create restrained, README-ready charts from pipeline outputs."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs/assets"


def style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.titleweight": "bold",
            "figure.facecolor": "white",
            "axes.facecolor": "white",
        }
    )


def performance_chart() -> None:
    segmentation = pd.read_csv(ROOT / "outputs/segmentation.csv")
    retention = pd.read_csv(ROOT / "outputs/retention.csv")
    platforms = ["Android", "iOS", "PC"]
    crash_pre = [100 * segmentation.query("patch_version == 1.2 and platform == @p").iloc[0].crash_rate for p in platforms]
    crash_post = [100 * segmentation.query("patch_version == 1.3 and platform == @p").iloc[0].crash_rate for p in platforms]
    d7_pre = [100 * retention.query("cohort_period == 'pre_1.3' and platform == @p").iloc[0].d7_retention for p in platforms]
    d7_post = [100 * retention.query("cohort_period == 'post_1.3' and platform == @p").iloc[0].d7_retention for p in platforms]

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    x = range(len(platforms))
    width = 0.36
    for ax, before, after, title, ylabel in [
        (axes[0], crash_pre, crash_post, "Crash rate increased most on Android", "Sessions crashed (%)"),
        (axes[1], d7_pre, d7_post, "D7 retention weakened in post-1.3 cohorts", "D7 retention (%)"),
    ]:
        ax.bar([i - width / 2 for i in x], before, width, label="Pre / 1.2", color="#B8C4D6")
        ax.bar([i + width / 2 for i in x], after, width, label="Post / 1.3", color="#725AC1")
        ax.set_xticks(list(x), platforms)
        ax.set_ylabel(ylabel)
        ax.set_title(title, loc="left", fontsize=11)
        ax.grid(axis="y", alpha=0.2)
        ax.legend(frameon=False, fontsize=8)
    fig.suptitle("Veloura patch 1.3: aligned performance and retention signals", x=0.06, ha="left", fontsize=14, fontweight="bold")
    fig.text(0.06, 0.01, "Synthetic portfolio data. Association does not establish causation.", fontsize=8, color="#555555")
    fig.tight_layout(rect=[0, 0.04, 1, 0.92])
    fig.savefig(ASSETS / "performance_signal.png", dpi=170, bbox_inches="tight")
    plt.close(fig)


def engagement_chart() -> None:
    engagement = pd.read_csv(ROOT / "outputs/engagement.csv")
    grouped = engagement.groupby("companion_adopter").agg(players=("players", "sum"), retained=("d30_players", "sum"))
    rates = [100 * grouped.loc[0, "retained"] / grouped.loc[0, "players"], 100 * grouped.loc[1, "retained"] / grouped.loc[1, "players"]]
    feedback = pd.read_csv(ROOT / "outputs/feedback_topics.csv")
    post = feedback[feedback.patch_version == 1.3].sort_values("feedback_count", ascending=True)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    axes[0].bar(["Non-adopter", "Adopter"], rates, color=["#B8C4D6", "#E06C9F"])
    axes[0].set_ylabel("D30 retention (%)")
    axes[0].set_title("Companion adoption is a retention marker", loc="left", fontsize=11)
    axes[0].grid(axis="y", alpha=0.2)
    axes[1].barh(post.topic, post.feedback_count, color="#725AC1")
    axes[1].set_xlabel("Feedback rows")
    axes[1].set_title("Post-1.3 feedback is performance-heavy", loc="left", fontsize=11)
    axes[1].grid(axis="x", alpha=0.2)
    fig.suptitle("Product opportunity signals", x=0.06, ha="left", fontsize=14, fontweight="bold")
    fig.text(0.06, 0.01, "Synthetic first-party data. Companion comparison is subject to self-selection.", fontsize=8, color="#555555")
    fig.tight_layout(rect=[0, 0.04, 1, 0.92])
    fig.savefig(ASSETS / "engagement_signal.png", dpi=170, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    style()
    performance_chart()
    engagement_chart()
    print(f"Saved charts to {ASSETS}")


if __name__ == "__main__":
    main()
