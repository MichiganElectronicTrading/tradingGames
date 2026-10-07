"""Local persistence under ~/.mtt_games/ (override with the MTT_GAMES_HOME env var)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def base_dir() -> Path:
    return Path(os.environ.get("MTT_GAMES_HOME") or Path.home() / ".mtt_games")


def _path(name: str) -> Path:
    path = base_dir() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def append_jsonl(name: str, record: dict[str, Any]) -> Path:
    path = _path(name)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return path


def read_jsonl(name: str) -> list[dict[str, Any]]:
    path = base_dir() / name
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # skip a corrupt line rather than losing the whole history
    return records


def delete(name: str) -> None:
    """Remove a stored file (no-op if it doesn't exist)."""
    (base_dir() / name).unlink(missing_ok=True)


def read_json(name: str, default: Any) -> Any:
    path = base_dir() / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(name: str, data: Any) -> Path:
    path = _path(name)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path
