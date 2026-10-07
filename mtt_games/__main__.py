"""`mtt-games` / `python -m mtt_games` entry point."""

from __future__ import annotations

import argparse

from mtt_games.app import GAMES, MTTGamesApp


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="mtt-games",
        description="MTT Games — solo trading drills in your terminal. Run with no arguments to open the game list.",
        epilog="example: mtt-games card --seed 42   (everyone on the same seed sees the same deals and quotes)",
    )
    parser.add_argument(
        "game", nargs="?", choices=[g.key for g in GAMES],
        help="open this game's lobby directly, skipping the home screen",
    )
    parser.add_argument(
        "--seed", type=int, metavar="INT",
        help="seed for every session this run (shown on the recap); default: a new random seed per session",
    )
    return parser.parse_args(argv)


def build_app(args: argparse.Namespace) -> MTTGamesApp:
    return MTTGamesApp(seed=args.seed, game=args.game)


def main(argv: list[str] | None = None) -> None:
    build_app(parse_args(argv)).run()


if __name__ == "__main__":
    main()
