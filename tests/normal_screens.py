"""Drives each Mental Math run screen through the same fixed steps on a fake clock and records what every Static
shows (and each widget's size). Used to prove that with every setting at NORMAL the screens render exactly as they did
before the Settings screen existed (the reference is tests/snapshots/math_normal_screens.json)."""

import io

from rich.console import Console
from textual.widgets import Static

from met_games.__main__ import build_app, parse_args

SIZE = (150, 50)
RUNS = {
    "sprint": ["math", "--mode", "sprint", "--seed", "5"],
    "optiver": ["math", "--mode", "optiver", "--seed", "3"],
    "chain": ["math", "--mode", "chain", "--seed", "4"],
    "chain_hard": ["math", "--mode", "chain", "--difficulty", "hard", "--seed", "9"],
    "estimate": ["math", "--mode", "estimate", "--seed", "2"],
    "flow": ["math", "--mode", "flow", "--seed", "3"],
    "prob": ["math", "--mode", "prob", "--difficulty", "hard", "--seed", "2"],
    "survival": ["math", "--mode", "survival", "--seed", "8"],
}


class Clock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


def styled(content, width: int) -> str:
    """The content as Rich prints it at this width, styles included (ANSI)."""
    buf = io.StringIO()
    Console(width=max(width, 1), file=buf, color_system="truecolor", force_terminal=True, legacy_windows=False,
            soft_wrap=False).print(content, end="")
    return buf.getvalue()


def dump(screen) -> list[str]:
    """Every Static with an id: its size and what it shows."""
    return [f"{w.id} {w.size.width}x{w.size.height} :: {styled(w.content, w.content_size.width)}"
            for w in screen.query(Static) if w.id]


async def capture() -> dict[str, list[list[str]]]:
    result = {}
    for name, argv in RUNS.items():
        app = build_app(parse_args(argv))
        clock = Clock()
        app.math_clock = clock
        frames = []
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            screen = app.screen
            run = screen.run
            frames.append(dump(screen))
            for step in range(3):
                clock.t += 2
                if name == "optiver":
                    await pilot.press(str(run.question.correct + 1))
                elif name in ("chain", "chain_hard"):
                    await pilot.press(*str(run.link.answer)[:-1])  # part-typed
                    await pilot.pause()
                    frames.append(dump(screen))
                    await pilot.press(*str(run.link.answer)[-1], "enter")
                elif name == "estimate":
                    await pilot.press("1", "2", "3")
                    await pilot.pause()
                    frames.append(dump(screen))
                    await pilot.press("enter")
                elif name in ("flow", "prob"):
                    await pilot.press(*run.problem.answer_text.replace(",", "")[:2])
                    await pilot.pause()
                    frames.append(dump(screen))
                    await pilot.press("enter")
                else:
                    text = run.problem.answer_text
                    await pilot.press(*text[:-1])
                    await pilot.pause()
                    frames.append(dump(screen))
                    await pilot.press(text[-1])
                await pilot.pause()
                screen.sync()
                await pilot.pause()
                frames.append(dump(screen))
        result[name] = frames
    return result
