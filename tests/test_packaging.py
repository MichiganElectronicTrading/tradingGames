"""Release packaging: one version (pyproject.toml), `met-games --version`, and no writes inside the install directory."""

import ast
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

import met_games
from met_games.__main__ import parse_args

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "met_games"


def pyproject_version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def test_version_comes_from_pyproject():
    assert met_games.__version__ == pyproject_version() == "0.1.0"


def test_version_flag_prints_and_exits_zero(capsys):
    with pytest.raises(SystemExit) as exit_info:
        parse_args(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out == "met-games 0.1.0\n"


def test_version_flag_from_the_command_line_skips_the_app(tmp_path):
    # A real process: if the TUI started, this would hang until the timeout instead of exiting.
    env = {"MET_GAMES_HOME": str(tmp_path), "PATH": ""}
    result = subprocess.run([sys.executable, "-m", "met_games", "--version"], capture_output=True, text=True,
                            timeout=30, env=env, cwd=tmp_path)
    assert result.returncode == 0
    assert result.stdout == "met-games 0.1.0\n"
    assert list(tmp_path.iterdir()) == []  # not even the data folder is created


# ── nothing writes inside the install directory ───────────────────────────────

# Names that only ever mean a filesystem write here (not str.replace, list.copy and the like).
WRITE_ATTRS = {"write_text", "write_bytes", "mkdir", "makedirs", "touch", "unlink", "copytree", "copy2", "copyfile",
               "rmtree", "mkstemp", "mkdtemp", "NamedTemporaryFile"}


def write_calls(tree: ast.AST):
    """Yield every call in the tree that can create or change a file."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name in WRITE_ATTRS:
            yield node
        elif name == "open":
            # open(path, mode) or path.open(mode)
            positional = node.args[1:2] if isinstance(func, ast.Name) else node.args[:1]
            mode = next((k.value for k in node.keywords if k.arg == "mode"), positional[0] if positional else None)
            if isinstance(mode, ast.Constant) and any(m in str(mode.value) for m in "wax+"):
                yield node


def package_modules():
    return sorted(p for p in PACKAGE.rglob("*.py") if "__pycache__" not in p.parts)


def test_no_module_locates_files_relative_to_the_install():
    # __file__ / importlib.resources paths point into the install; reading package data that way would be fine,
    # but nothing needs it today, so any use is flagged for a look.
    for path in package_modules():
        source = path.read_text(encoding="utf-8")
        assert "__file__" not in source, path
        assert "importlib.resources" not in source, path


def test_files_are_written_only_by_storage_or_to_the_working_directory():
    """storage.py writes under ~/.met_games (or MET_GAMES_HOME). The only other writes are the recap CSV exports,
    which the player asks for with a key and which go to the current directory. Anything else is a failure."""
    offenders = []
    for path in package_modules():
        if path == PACKAGE / "storage.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for func in (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
            calls = list(write_calls(func))
            if calls and "Path.cwd()" not in ast.unparse(func):
                offenders += [f"{path.relative_to(ROOT)}:{c.lineno} {ast.unparse(c)}" for c in calls]
    assert offenders == []


def test_storage_writes_only_under_its_base_dir(tmp_path, monkeypatch):
    from met_games import storage

    monkeypatch.setenv("MET_GAMES_HOME", str(tmp_path / "data"))
    assert storage.write_json("sub/x.json", {}).is_relative_to(tmp_path / "data")
    assert storage.append_jsonl("y.jsonl", {}).is_relative_to(tmp_path / "data")
