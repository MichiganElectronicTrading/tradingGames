"""The rename to met-games: data-folder migration, the old env var as a fallback, and the old command alias.
Every test runs on a temp HOME, never the real one."""

import pytest

from met_games import __main__ as entry
from met_games import storage

OLD_NOTICE = "mtt-games is now met-games — this alias will be removed in a future version."


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("MET_GAMES_HOME", raising=False)
    monkeypatch.delenv(storage.LEGACY_ENV, raising=False)
    return tmp_path


def legacy_folder(home):
    old = home / storage.LEGACY_DIR
    old.mkdir()
    (old / "card_history.jsonl").write_text('{"score": 1}\n')
    (old / "hilo_scores.json").write_text('{"interview/EASY": []}')
    return old


def test_migration_copies_files_and_leaves_the_old_folder_intact(home):
    old = legacy_folder(home)
    assert storage.migrate_legacy() is True
    new = home / storage.DIR
    assert storage.base_dir() == new
    for name in ("card_history.jsonl", "hilo_scores.json"):
        assert (new / name).read_text() == (old / name).read_text()
    assert sorted(p.name for p in old.iterdir()) == ["card_history.jsonl", "hilo_scores.json"]  # untouched
    assert storage.read_jsonl("card_history.jsonl") == [{"score": 1}]
    assert storage.migrate_legacy() is False  # one time only


def test_no_migration_when_the_new_folder_exists(home):
    legacy_folder(home)
    new = home / storage.DIR
    new.mkdir()
    (new / "card_history.jsonl").write_text('{"score": 2}\n')
    assert storage.migrate_legacy() is False
    assert sorted(p.name for p in new.iterdir()) == ["card_history.jsonl"]
    assert storage.read_jsonl("card_history.jsonl") == [{"score": 2}]


def test_no_migration_without_an_old_folder(home):
    assert storage.migrate_legacy() is False
    assert not (home / storage.DIR).exists()


def test_old_env_var_is_a_fallback(home, monkeypatch):
    monkeypatch.setenv(storage.LEGACY_ENV, str(home / "old"))
    assert storage.base_dir() == home / "old"
    monkeypatch.setenv("MET_GAMES_HOME", str(home / "new"))
    assert storage.base_dir() == home / "new"


class FakeApp:
    ran = False

    def run(self):
        FakeApp.ran = True


def test_startup_migrates_and_prints_one_dim_line(home, monkeypatch, capsys):
    legacy_folder(home)
    monkeypatch.setattr(entry, "build_app", lambda args: FakeApp())
    entry.main([])
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1 and "migrated" in out[0] and FakeApp.ran
    assert (home / storage.DIR / "hilo_scores.json").exists()
    entry.main([])
    assert capsys.readouterr().out == ""  # nothing to migrate the second time


def test_mtt_games_alias_prints_the_notice_then_runs_the_same_app(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(entry, "main", lambda argv=None: calls.append(argv))
    entry.legacy_main(["card", "--seed", "3"])
    assert capsys.readouterr().out.strip() == OLD_NOTICE
    assert calls == [["card", "--seed", "3"]]
