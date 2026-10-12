"""`met-games` / `python -m met_games` entry point, plus the old `mtt-games` alias."""

from __future__ import annotations

import argparse

from rich.console import Console

from met_games import storage
from met_games.app import GAMES, METGamesApp


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="met-games",
        description="MET Games — solo trading drills in your terminal. Run with no arguments to open the game list.",
        epilog="example: met-games card --seed 42   (everyone on the same seed sees the same deals and quotes)",
        # keep the help column where it was before the longer math flags; those wrap onto their own line
        formatter_class=lambda prog: argparse.HelpFormatter(prog, max_help_position=16),
    )
    parser.add_argument(
        "game", nargs="?", choices=[g.key for g in GAMES], metavar="GAME",
        help="open this game's lobby directly, skipping the home screen (" + ", ".join(g.key for g in GAMES) + ")",
    )
    parser.add_argument(
        "--seed", type=int, metavar="INT",
        help="seed for every session this run (shown on the recap); default: a new random seed per session",
    )
    parser.add_argument(
        "--deck", choices=["interview", "full", "redblack"], metavar="DECK",
        help="hilo only: the deck to start on — interview, full or redblack (default: the difficulty's deck)",
    )
    parser.add_argument(
        "--mode", choices=["sprint", "survival", "zetamac", "optiver"], metavar="MODE",
        help="math only: start this mode straight away — sprint, survival, zetamac or optiver",
    )
    parser.add_argument(
        "--difficulty", choices=["easy", "medium", "hard"], metavar="LEVEL",
        help="math only: the difficulty for sprint and survival — easy, medium or hard (default: medium)",
    )
    parser.add_argument("--daily", action="store_true", help="math only: open today's daily challenge")
    args = parser.parse_args(argv)
    if args.daily and args.game is None:
        args.game = "math"
    return args


def build_app(args: argparse.Namespace) -> METGamesApp:
    return METGamesApp(seed=args.seed, game=args.game, deck=args.deck, math_mode=getattr(args, "mode", None),
                       math_difficulty=getattr(args, "difficulty", None), math_daily=getattr(args, "daily", False))


def notice(line: str) -> None:
    """One dim line on the terminal before the app takes over the screen."""
    Console(highlight=False, soft_wrap=True).print(line, style="dim")


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if storage.migrate_legacy():
        notice(f"migrated your history from ~/{storage.LEGACY_DIR} to ~/{storage.DIR} (the old folder is untouched)")
    build_app(args).run()


def legacy_main(argv: list[str] | None = None) -> None:
    """The pre-rename `mtt-games` command: same app, one notice first. To be removed in a future version."""
    notice("mtt-games is now met-games — this alias will be removed in a future version.")
    main(argv)


if __name__ == "__main__":
    main()
