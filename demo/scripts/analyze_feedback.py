#!/usr/bin/env python3
"""Transparent rule-based topic classification for first-party and market feedback."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd


TAXONOMY = {
    "Performance": ["crash", "lag", "frame", "loading", "overheat", "disconnect", "stutter", "fps", "optimi"],
    "Monetization": ["price", "expensive", "pity", "pull", "gacha", "paywall", "currency", "monetization", "cash shop"],
    "Fashion": ["outfit", "wardrobe", "dye", "clipping", "styling", "dress", "cosmetic", "costume"],
    "Combat": ["combat", "boss", "dodge", "weapon", "difficulty", "targeting", "enemy"],
    "Companion": ["companion", "affinity", "bond", "dialogue", "romance", "relationship", "villager"],
    "Content": ["quest", "story", "map", "exploration", "event", "repetitive", "endgame", "content"],
    "UI/UX": ["menu", "interface", "navigation", "inventory", "controls", "ui", "ux"],
    "Social/MMO": ["guild", "co-op", "coop", "matchmaking", "chat", "server", "multiplayer"],
}


def classify(text: str) -> tuple[str, int]:
    normalized = re.sub(r"[^a-z0-9\s-]", " ", str(text).lower())
    scores = {topic: sum(normalized.count(term) for term in terms) for topic, terms in TAXONOMY.items()}
    topic, score = max(scores.items(), key=lambda item: item[1])
    return (topic, score) if score else ("Other", 0)


def annotate(input_path: Path, output_path: Path, text_column: str) -> pd.DataFrame:
    frame = pd.read_csv(input_path)
    classified = frame[text_column].fillna("").map(classify)
    frame["topic"] = classified.map(lambda item: item[0])
    frame["keyword_hits"] = classified.map(lambda item: item[1])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False)
    return frame


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--text-column", default="feedback_text")
    args = parser.parse_args()
    result = annotate(args.input, args.output, args.text_column)
    print(result["topic"].value_counts().to_string())


if __name__ == "__main__":
    main()
