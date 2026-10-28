"""MET Games — solo trading drills in your terminal."""

from importlib.metadata import PackageNotFoundError, version

# The version lives only in pyproject.toml; this reads it back from the installed package's metadata.
try:
    __version__ = version("met-games")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0+unknown"
