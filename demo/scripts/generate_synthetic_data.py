#!/usr/bin/env python3
"""Generate deterministic product telemetry for the fictional game Veloura."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


PATCH_DATE = pd.Timestamp("2026-03-01")
OBSERVATION_END = pd.Timestamp("2026-05-31")


def patch_for(date: pd.Timestamp) -> str:
    return "1.3" if date >= PATCH_DATE else "1.2"


def generate(output_dir: Path, n_players: int = 2500, seed: int = 42) -> dict[str, int]:
    rng = np.random.default_rng(seed)
    output_dir.mkdir(parents=True, exist_ok=True)

    signup_dates = pd.to_datetime(
        rng.choice(pd.date_range("2026-01-01", "2026-04-25"), n_players)
    )
    platforms = rng.choice(["Android", "iOS", "PC"], n_players, p=[0.47, 0.32, 0.21])
    personas = rng.choice(
        ["fashion_collector", "combat_explorer", "companion_fan", "social_casual"],
        n_players,
        p=[0.34, 0.28, 0.23, 0.15],
    )
    players = pd.DataFrame(
        {
            "player_id": [f"P{i:05d}" for i in range(1, n_players + 1)],
            "signup_date": signup_dates,
            "region": rng.choice(["NA", "EU", "SEA"], n_players, p=[0.38, 0.37, 0.25]),
            "platform": platforms,
            "acquisition_channel": rng.choice(
                ["organic", "creator", "paid_social", "store_feature"],
                n_players,
                p=[0.34, 0.22, 0.28, 0.16],
            ),
            "age_band": rng.choice(["18-24", "25-34", "35+"], n_players, p=[0.44, 0.39, 0.17]),
            "persona": personas,
        }
    ).sort_values("player_id")

    sessions: list[dict] = []
    events: list[dict] = []
    payments: list[dict] = []
    feedback: list[dict] = []
    session_id = event_id = payment_id = feedback_id = 1

    feedback_templates = {
        "performance": [
            "The open world keeps crashing after the update on my phone.",
            "Frame rate drops badly during city combat and loading takes forever.",
            "I get disconnected whenever a world boss starts.",
            "My phone overheats and the game lags while exploring the new map.",
        ],
        "monetization": [
            "The limited outfit is beautiful but the price is too expensive.",
            "The gacha pity feels unclear and pulls cost too much currency.",
            "I joined the styling event but the premium dress feels paywalled.",
            "Monthly pass value is fine, but direct outfit pricing is hard to justify.",
        ],
        "companion": [
            "Companion dialogue repeats too often after raising affinity.",
            "I love the bond scenes and want more companion interactions.",
            "Affinity progression is comforting but the daily cap feels restrictive.",
        ],
        "fashion": [
            "The wardrobe is gorgeous but sleeves clip during combat.",
            "Please add more dye slots and better outfit filtering.",
            "Styling is my favourite feature and the new set looks amazing.",
        ],
        "combat": [
            "Targeting switches enemies during boss combat and dodging feels delayed.",
            "The new boss is challenging but the weapon mechanics are satisfying.",
            "Combat difficulty spikes too sharply in the new region.",
        ],
        "content": [
            "The new map is beautiful but side quests become repetitive.",
            "I enjoyed the story event and exploration rewards.",
            "There is not enough endgame content after finishing the main quest.",
        ],
    }

    for row in players.itertuples(index=False):
        signup = pd.Timestamp(row.signup_date)
        max_day = min(60, (OBSERVATION_END - signup).days)
        companion_adopter = row.persona == "companion_fan" or rng.random() < 0.29
        outfit_participant = row.persona == "fashion_collector" or rng.random() < 0.35

        active_days = {0}
        for day in range(1, max_day + 1):
            base = 0.54 * np.exp(-day / 24) + 0.055
            if companion_adopter and day >= 3:
                base += 0.075
            if row.persona == "combat_explorer":
                base += 0.025
            date = signup + pd.Timedelta(days=day)
            if date >= PATCH_DATE and row.platform == "Android":
                base -= 0.10
            elif date >= PATCH_DATE and row.platform == "iOS":
                base -= 0.035
            if date.weekday() >= 5:
                base += 0.035
            if rng.random() < max(0.015, min(base, 0.92)):
                active_days.add(day)

        if companion_adopter and max_day >= 3:
            date = signup + pd.Timedelta(days=int(rng.integers(2, min(8, max_day + 1))))
            events.append(
                {"event_id": f"E{event_id:07d}", "player_id": row.player_id,
                 "event_date": date, "event_name": "companion_affinity_unlocked",
                 "event_value": int(rng.integers(1, 6)), "patch_version": patch_for(date)}
            )
            event_id += 1

        if outfit_participant:
            event_date = max(signup, pd.Timestamp("2026-03-15")) + pd.Timedelta(days=int(rng.integers(0, 21)))
            if event_date <= OBSERVATION_END:
                active_days.add((event_date - signup).days)
                events.append(
                    {"event_id": f"E{event_id:07d}", "player_id": row.player_id,
                     "event_date": event_date, "event_name": "celestial_runway_joined",
                     "event_value": int(rng.integers(1, 9)), "patch_version": patch_for(event_date)}
                )
                event_id += 1

        crashed_any = False
        for day in sorted(d for d in active_days if 0 <= d <= max_day):
            date = signup + pd.Timedelta(days=day)
            n_sessions = 1 + int(rng.random() < 0.22)
            for _ in range(n_sessions):
                crash_probability = 0.012
                if date >= PATCH_DATE and row.platform == "Android":
                    crash_probability = 0.105
                elif date >= PATCH_DATE and row.platform == "iOS":
                    crash_probability = 0.045
                elif date >= PATCH_DATE and row.platform == "PC":
                    crash_probability = 0.018
                crashed = int(rng.random() < crash_probability)
                crashed_any = crashed_any or bool(crashed)
                mode_weights = {
                    "fashion_collector": [0.39, 0.24, 0.22, 0.15],
                    "combat_explorer": [0.16, 0.48, 0.24, 0.12],
                    "companion_fan": [0.19, 0.21, 0.19, 0.41],
                    "social_casual": [0.25, 0.22, 0.35, 0.18],
                }[row.persona]
                duration = max(2, rng.normal(38, 17) * (0.55 if crashed else 1.0))
                sessions.append(
                    {"session_id": f"S{session_id:08d}", "player_id": row.player_id,
                     "session_date": date, "duration_minutes": round(float(duration), 1),
                     "primary_mode": rng.choice(["fashion", "combat", "exploration", "companion"], p=mode_weights),
                     "patch_version": patch_for(date), "crashed": crashed}
                )
                session_id += 1

        payer_probability = 0.07 + (0.10 if row.persona == "fashion_collector" else 0) + (0.06 if row.persona == "companion_fan" else 0)
        if rng.random() < payer_probability:
            n_tx = int(rng.integers(1, 4))
            for _ in range(n_tx):
                day = int(rng.choice(sorted(active_days)))
                date = signup + pd.Timedelta(days=day)
                product = rng.choice(["gacha_currency", "monthly_pass", "outfit"], p=[0.50, 0.32, 0.18])
                amount = {
                    "gacha_currency": rng.choice([4.99, 14.99, 29.99, 49.99]),
                    "monthly_pass": 9.99,
                    "outfit": rng.choice([19.99, 29.99]),
                }[product]
                payments.append(
                    {"payment_id": f"T{payment_id:06d}", "player_id": row.player_id,
                     "payment_date": date, "product_type": product,
                     "amount_usd": float(amount), "patch_version": patch_for(date)}
                )
                payment_id += 1

        if rng.random() < 0.27:
            if crashed_any and rng.random() < 0.70:
                topic, rating = "performance", int(rng.choice([1, 1, 2]))
            elif outfit_participant and rng.random() < 0.42:
                topic, rating = "monetization", int(rng.choice([1, 2, 2, 3]))
            else:
                topic = rng.choice(["companion", "fashion", "combat", "content"])
                rating = int(rng.choice([2, 3, 4, 5], p=[0.12, 0.25, 0.38, 0.25]))
            date = signup + pd.Timedelta(days=int(rng.choice(sorted(active_days))))
            feedback.append(
                {"feedback_id": f"F{feedback_id:06d}", "player_id": row.player_id,
                 "feedback_date": date, "rating": rating,
                 "feedback_text": rng.choice(feedback_templates[topic]),
                 "patch_version": patch_for(date)}
            )
            feedback_id += 1

    frames = {
        "players": players,
        "sessions": pd.DataFrame(sessions),
        "payments": pd.DataFrame(payments),
        "gameplay_events": pd.DataFrame(events),
        "feedback": pd.DataFrame(feedback),
    }
    for name, frame in frames.items():
        for column in frame.columns:
            if "date" in column:
                frame[column] = pd.to_datetime(frame[column]).dt.strftime("%Y-%m-%d")
        frame.to_csv(output_dir / f"{name}.csv", index=False)
    return {name: len(frame) for name, frame in frames.items()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("data/synthetic"))
    parser.add_argument("--players", type=int, default=2500)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    counts = generate(args.output_dir, args.players, args.seed)
    print("Generated:", ", ".join(f"{k}={v}" for k, v in counts.items()))


if __name__ == "__main__":
    main()
