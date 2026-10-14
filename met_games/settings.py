"""Suite-wide settings in ~/.met_games/settings.json (MET_GAMES_HOME respected), one namespace per game:
{"math": {"problem_size": "normal", "answer_size": "normal"}}. Saved on every change. A missing or corrupt file reads
as all defaults (never an error) and is rewritten whole on the next save. Keys this version doesn't know are kept."""

from __future__ import annotations

from typing import Any

from met_games import storage

SETTINGS_FILE = "settings.json"


def load() -> dict[str, Any]:
    try:
        data = storage.read_json(SETTINGS_FILE, {})
    except (OSError, ValueError):  # unreadable (not UTF-8, a directory, …): defaults
        return {}
    return data if isinstance(data, dict) else {}


def get(game: str, key: str, default: Any) -> Any:
    section = load().get(game)
    return section.get(key, default) if isinstance(section, dict) else default


def set(game: str, key: str, value: Any) -> None:  # noqa: A001 — the store's verb
    data = load()
    section = data.get(game)
    if not isinstance(section, dict):
        section = data[game] = {}
    section[key] = value
    storage.write_json(SETTINGS_FILE, data)
