"""Local persistence under ~/.met_games/ (override with the MET_GAMES_HOME env var)."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

DIR = ".met_games"
# Before the rename to MET the folder was ~/.mtt_games and the env var MTT_GAMES_HOME. The env var is still
# honored when MET_GAMES_HOME is unset, and the old folder is copied over once (see migrate_legacy).
LEGACY_DIR = ".mtt_games"
LEGACY_ENV = "MTT_GAMES_HOME"


def base_dir() -> Path:
    override = os.environ.get("MET_GAMES_HOME") or os.environ.get(LEGACY_ENV)
    return Path(override) if override else Path.home() / DIR


def migrate_legacy(home: Path | None = None) -> bool:
    """One-time migration: if ~/.met_games doesn't exist and ~/.mtt_games does, copy every file across.
    Never moves or deletes the old folder. Skipped when an env var points the data somewhere else.
    Returns True if it copied."""
    if home is None:
        if os.environ.get("MET_GAMES_HOME") or os.environ.get(LEGACY_ENV):
            return False
        home = Path.home()
    new, old = home / DIR, home / LEGACY_DIR
    if new.exists() or not old.is_dir():
        return False
    shutil.copytree(old, new)
    return True


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


def read_history(name: str) -> list[dict[str, Any]]:
    """A history file without its `"abandoned": true` lines (games left from the pause menu)."""
    return [r for r in read_jsonl(name) if not r.get("abandoned")]


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
