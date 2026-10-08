#!/usr/bin/env python3
"""Validate the three live Issue 1–5 foundation examples."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = {
    "infinity-nikki.json": "game_",
    "pubg-battlegrounds.json": "game_",
    "counter-strike-2.json": "game_",
}


def validate() -> list[str]:
    errors: list[str] = []
    game_ids: set[str] = set()
    for filename, game_prefix in EXAMPLES.items():
        path = ROOT / "examples/foundation" / filename
        if not path.exists():
            errors.append(f"missing example: {filename}")
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        resolution = payload["resolution"]
        if resolution["status"] != "resolved" or not resolution.get("game"):
            errors.append(f"{filename}: not resolved")
            continue
        game = resolution["game"]
        game_ids.add(game["game_id"])
        if not game["game_id"].startswith(game_prefix):
            errors.append(f"{filename}: invalid game ID")
        if not game["resolution_evidence_ids"]:
            errors.append(f"{filename}: identity has no evidence")

        aliases = payload["aliases"]["aliases"]
        observations = payload["aliases"]["observations"]
        observation_by_text = {item["text"]: item for item in observations}
        for alias in aliases:
            if not alias["source_evidence_ids"]:
                errors.append(f"{filename}: alias {alias['text']!r} has no evidence")
            if alias["alias_type"] not in {"official_title", "localized_title"}:
                observation = observation_by_text.get(alias["text"])
                if not observation or not observation["source_references"] or not observation["source_excerpts"]:
                    errors.append(f"{filename}: discovered alias {alias['text']!r} lacks source reference")
            if alias["ambiguity"] == "high":
                if alias["standalone_search_safe"]:
                    errors.append(f"{filename}: high-ambiguity alias marked standalone-safe")
                for plan in payload["query_plans"]:
                    if alias["alias_id"] in plan["alias_ids"] and not plan["disambiguators"]:
                        errors.append(f"{filename}: high-ambiguity alias used without disambiguator")

        fact_bundle = payload["fact_bundle"]
        evidence_ids = {item["evidence_id"] for item in fact_bundle["evidence"]}
        if not fact_bundle["facts"]:
            errors.append(f"{filename}: no facts retrieved")
        for fact in fact_bundle["facts"]:
            if fact["source_evidence_id"] not in evidence_ids:
                errors.append(f"{filename}: fact {fact['fact_id']} has broken evidence link")
        if any(item["evidence_kind"] not in {"fact_source", "official", "patch_note"} for item in fact_bundle["evidence"]):
            errors.append(f"{filename}: UGC evidence leaked into Fact Layer")

    if len(game_ids) != len(EXAMPLES):
        errors.append("examples did not resolve to three distinct canonical games")
    return errors


if __name__ == "__main__":
    failures = validate()
    if failures:
        raise SystemExit("\n".join(failures))
    print(f"Validated {len(EXAMPLES)} live foundation examples")
