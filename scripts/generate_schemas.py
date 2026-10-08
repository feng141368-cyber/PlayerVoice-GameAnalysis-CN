#!/usr/bin/env python3
"""Generate deterministic JSON Schemas for public PlayerVoice contracts."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gamepulse.models import SCHEMA_MODELS  # noqa: E402


def generate(output_dir: Path = ROOT / "schemas") -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, model in sorted(SCHEMA_MODELS.items()):
        path = output_dir / filename
        content = json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


if __name__ == "__main__":
    for generated in generate():
        print(generated.relative_to(ROOT))
