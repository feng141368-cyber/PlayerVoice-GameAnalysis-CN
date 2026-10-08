from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def load_config(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or not config.get("project", {}).get("game"):
        raise ValueError("Config must define project.game")
    return config


def env(name: str) -> str | None:
    value = os.environ.get(name)
    return value if value and value.strip() else None
