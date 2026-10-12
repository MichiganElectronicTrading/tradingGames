# MET Trading Games — Michigan Electronic Trading

Solo trading drills for **MET (Michigan Electronic Trading)**, in your terminal.

There are three games. Card and Dice are market-taking drills built on the same core:

- **Card Game**: cards are dealt from a deck and prices are whole dollars.
- **Dice Game**: dice are rolled and prices move in **0.25 ticks**.
- **Trading Game**: a market-making drill. You and three computer traders take turns making two-way markets on one deal of cards; see [Trading Game](#trading-game).

In Card and Dice, some items are face up. A market maker quotes a two-way price on the sum of all of them, and you buy, sell, or pass before the timer runs out. After the reveal you report your own P&L. The game then grades your decision on **edge** (was it a good trade at the time?) separately from **luck** (how the draw went).

## Install & run

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv run met-games            # run from the repo (creates the venv on first run)
# or install it as a tool:
uv tool install .
met-games
```

`python -m met_games` also works inside the venv. Run the tests with `uv run pytest`.

The app opens on the **MET GAMES** home screen, which lists the available games. Press ⏎ on a game to reach its lobby.

```bash
met-games card              # skip the home screen and open the Card Game lobby
met-games dice              # ... or the Dice Game lobby
met-games trade             # ... or the Trading Game lobby
met-games dice --seed 42    # every session this run uses seed 42
met-games --help
```

## Upgrading from mtt-games

This project used to be **mtt-games**, for MTT (Michigan Trading and Technology). It is now **met-games**, for MET (Michigan Electronic Trading). Seeds are unchanged, so `--seed N` deals the same game as before. On first run, your history is copied from `~/.mtt_games` to `~/.met_games`; the old folder is left in place. `MTT_GAMES_HOME` still works if `MET_GAMES_HOME` is unset. To swap the installed command:

```bash
uv tool uninstall mtt-games
uv tool install --force --editable .
```

## Club play

To run a head-to-head drill, pick a seed and have everyone run the same command:

```bash
met-games card --seed 1234      # or: met-games dice --seed 1234 / met-games trade --seed 1234
```

Everyone then plays the same game and mode. With the same seed, everyone gets identical deals, events, flips and quotes, so the only differences are the decisions people make. When the session ends, compare recaps; each one shows `SEED 1234` in its top bar. FINAL BALANCE shows who made the most money, but EDGE TAKEN is the fairer score, since LUCK is the same draw for everyone. Pressing R on the recap replays the seed for a rematch.


## The games

Card Game: Trading against a market on hidden card values

Dice: Game: Trading against a market on hidden dice values with smaller tick sizing

Trading Game: Making a market and taking against bot markets on hidden card values

Outcry: Open market outcry across different rounds, trading a contracts hidden true value.

ETF Arb: Price a basket of stocks and race 3 traders to trade the ETF when it drifts from its NAV

Hi/Lo: Call the next card higher or lower (or red or black) and size each even-money bet by the Kelly criterion, against the clock

Math: Mental math drills with exact answers — arcade sprints, Zetamac and Optiver-style test drills, a weakness report, and a daily challenge

## Controls everywhere

- **Esc — pause menu.** On any in-game screen (from a game's start to its results) Esc opens PAUSED: `[R] resume · [L] leave to lobby · [Q] quit met-games`; Esc again resumes. The clock stops and the computer traders freeze while it's open, and it covers the whole board, so it can't buy free thinking time. Esc works even while you're typing in a box (a priority binding).
- **L asks once more** — "Leave this game? Progress won't be saved. [Y/N]". Y returns to that game's own lobby with your mode and difficulty still selected; N goes back to the menu. A game you leave isn't saved anywhere — no history, high score, best, stats or daily streak — apart from one `"abandoned": true` line in the game's history file, which stats skip.
- **Exception — the Math daily:** the menu says "daily clock keeps running", and leaving ends the attempt with the score so far: it uses today's attempt, is logged, and the report shows ENDED EARLY.
- **Results / recap screens** keep their L and Q keys; Esc there goes straight to the game's lobby.
- **Ctrl+C quits** from anywhere, including inside a text box.
- Every in-game key bar ends with `Esc menu`.

**Key changes for the pause menu**

| game | screen | was | now |
|---|---|---|---|
| Outcry | open outcry | Esc cancels all orders | **Ctrl+X** cancels all (typing `x` still works); Esc = menu |
| ETF Arb | round | Esc quits to the lobby | menu → L → Y |
| Math | run (Sprint, Survival, Zetamac, drill, daily) and Optiver-style | Esc ends the run (scored) | **Ctrl+E** ends the run; Esc = menu |
| Card, Dice, Trading Game, Outcry, ETF, Hi/Lo, Math | results / recap | Esc did nothing (Math: lobby) | Esc → lobby |

## Higher or Lower

```bash
met-games hilo                      # lobby: EASY · MEDIUM · HARD · RED/BLACK · CUSTOM…
met-games hilo --seed 7 --deck full # same deck order for everyone; --deck interview|full|redblack
```

**Rules.** One card is showing. Call the next card HIGHER or LOWER and stake a whole percent of your capital (0 = sit out). Bets pay even money. A same-rank card is a push. Aces are low (A=1 … K=13). Keys: H/L (or R/B) pick the side; 0–9 stake 0–90%; A goes all-in; ←→ adds or removes 5%; ⏎ locks. With quick lock on, a stake key pressed after a side locks the bet immediately. If the clock runs out, the bet is a stake-0 MISS. If capital falls below 1 you bust, which ends the game.

**Kelly sizing.** Among the cards left, h are higher than the showing card, l are lower, and the rest are the same rank. On an even-money bet the Kelly fraction is **k = |h − l| ÷ (h + l)** on the side with more cards; a push returns the stake, so it doesn't change k. If h = l there is no edge and the right play is to sit out. On red/black, k = |reds − blacks| ÷ (reds + blacks).

**Grading.** Let s be your stake as a fraction of capital.

| grade | when | points |
|---|---|---|
| PERFECT | right side, \|s − k\| ≤ max(0.10k, 3%) | 100 |
| GOOD | right side, \|s − k\| ≤ max(0.25k, 7%) | 60 |
| OK | right side, further off | 20 |
| DISCIPLINE | no edge and you sat out | 50 |
| SAT OUT | there was an edge and you sat out | 0 |
| MISS | wrong side, staked with no edge, or timed out | 0 |

**Scoring.** Points = base × speed × combo, rounded half up.
- **Speed:** LIGHTNING ×2 if you lock in the first 25% of the bet's clock; FAST ×1.5 in the first 50%. Speed only applies to PERFECT, GOOD and DISCIPLINE.
- **Combo:** ×(1 + 0.1 × streak), capped at ×3. PERFECT, GOOD and DISCIPLINE extend the streak; OK keeps it; MISS, SAT OUT and a timeout reset it.
- **End of game:** if you finish above your start without busting, you get a capital bonus of round(1000 × log2(final ÷ start)).
- **End screen:** shows your multiple next to the **Kelly benchmark** (staking exactly k on the right side every bet of the same deck order) and your **worst bet** (the most points lost against the best play).
- **High scores:** the top 10 for each deck and difficulty are kept in `~/.met_games/hilo_scores.json`.

**Decks.**

| deck | cards | bets |
|---|---|---|
| Interview | one of each rank, A–K | 12 |
| Full | 52 | 51 |
| Red/Black | 52, call the color | 52 |

**Difficulty.**

| | EASY | MEDIUM | HARD |
|---|---|---|---|
| default deck | Interview | Full | Full |
| time per bet | 10s | 6s | 4s |
| board shows | counts, lower/same/higher and odds | counts and lower/same/higher | cards left and the last three |

Press D in the lobby to switch decks.

### Decisions (Hi/Lo)

- **Lobby:** RED/BLACK is a shortcut for MEDIUM on the red/black deck. The deck picker keeps your choice once you press D (or pass `--deck`); otherwise each difficulty shows its default deck.
- **Interview deck:** the suit of each rank comes from the seed, so the same seed gives the same suits.
- **Red/black:** there is no showing card; you bet on all 52 cards.
- **Odds:** h, l and same are counted over every card left, including same-rank cards, which push.
- **Grading:** k = 0 is checked first, so any stake on a no-edge bet is a MISS.
- **Clock:** during the reveal flash (0.6s, or ⏎ to skip) the clock is paused; the next bet's clock starts when it opens.
- **Benchmark:** stakes are floored to whole dollars, to match how your own stakes are sized (capital × percent, floored).
- **Capital bonus:** measured against the starting capital; there is no bonus if you bust or finish at or below the start.
- **Rounding:** points round half up.
- **Worst bet:** measured against the best available grade at that bet's speed and combo. That is PERFECT, or DISCIPLINE on a no-edge bet, so a correct sit-out is never the worst bet.
- **High scores:**
  - Kept per deck and difficulty; CUSTOM games have their own board.
  - Ties keep the earlier score ahead.
  - The lobby's STATS entry is replaced by HIGH SCORES. Every finished game is also appended to `~/.met_games/hilo_history.jsonl`.
- **Shared code:** the Custom screen gained a `custom_note` hook (Hi/Lo has no settle range), and the CLI gained `--deck`.
- **Existing tests:** the only changes are the list-of-games assertions, which now include HI/LO.

### Decisions (rename)

- **Old command:** `mtt-games` still works as an alias. It runs the same app after printing one dim notice. **Remove it in a future version**, along with the `MTT_GAMES_HOME` fallback; the `~/.mtt_games` migration can go once everyone has upgraded.
- **Migration:** `~/.mtt_games` is copied (never moved or deleted) into `~/.met_games`, only when the new folder doesn't exist yet and no data-folder env var is set. One dim line on the terminal says it happened.
- **Line widths:** "MTT" → "MET" keeps every string's length. The home-screen title and the project description get 4 characters shorter, so nothing re-wraps and no padding was needed.
- **Seeds:** a test pins seed 1234's first deal in all six games to the values from before the rename.

## Mental Math

```bash
met-games math                                   # lobby: SPRINT · SURVIVAL · ZETAMAC · OPTIVER-STYLE · DAILY · MY STATS
met-games math --mode sprint --difficulty hard   # start a run straight away (--mode sprint|survival|zetamac|optiver)
met-games math --mode zetamac --seed 7           # same problems for everyone on seed 7
met-games math --daily                           # today's daily challenge
```

**Answering.** In Sprint, Survival, Zetamac, the drill and the daily, you type digits, `.`, `-` and `/`; Backspace erases. The answer locks the moment what you've typed is exactly equal to the answer: `13/16` and `0.8125` both match 13/16, and `.5` matches 0.5. There is no Enter and no wrong answer. Tab skips the problem, which resets the combo. Ctrl+E ends the run early (it's scored); Esc opens the pause menu. Optiver-style is multiple choice: 1–4 answers and moves straight on, S skips, and there is no going back.

**Modes.**

| mode | format | score |
|---|---|---|
| SPRINT | 2:00 (Custom: 0:30–5:00), as many as you can | correct + points |
| SURVIVAL | start with 0:30; correct +10s EASY · +8s MEDIUM · +6s HARD, skip −5s; every 10 correct the bonus drops 0.5s, down to half the start (+5s · +4s · +3s; Custom sets both); ends at 0:00 | correct + points |
| ZETAMAC 120s | the Zetamac default: (2–100) + (2–100), subtraction as reversed addition, (2–12) × (2–100), division as reversed multiplication; 120s | raw correct only, so it compares with your Zetamac scores |
| OPTIVER-STYLE 80/8 | unofficial practice format: 80 multiple-choice questions in 8:00 — decimals & fractions, percentages and arithmetic at medium–hard | NET = +1 right, −1 wrong, 0 skipped |
| DAILY | Sprint 2:00, MEDIUM, all four families, the same problems for everyone | correct + points, and a score card |

CHAIN, ESTIMATE, FLOW-STYLE and IMC/SIG-STYLE are listed as "soon" (v2). In Optiver-style, the PACE panel compares your average seconds per question with the pace you need to finish the rest; each question has four distinct options with exactly one right, and the three wrong ones are near-misses (a decimal place off, two digits swapped, a little off, or a common slip such as adding tops and bottoms of fractions).

**Problem families.** Every answer is exact (`Fraction`): whole numbers for core, at most 4 decimal places for decimals & fractions, at most 2 for percentages and desk math.

| family · base points | EASY | MEDIUM | HARD |
|---|---|---|---|
| core · 100 | 2-digit ±; × to 12×12; exact ÷ to 144÷12 | 3-digit ±; 2×2 and 3×1 digit ×; 3-digit ÷ 1-digit | 4-digit ±; 3×2 digit ×; ÷ by 2-digit |
| decimals & fractions · 150 | 1/2, 1/4, fifths ↔ decimals; 0.5 × 18, 0.25 × 44 | eighths; 0.375 × 48; fraction ± fraction (denominators ≤ 16) | sixteenths; 0.0625 × 72; 7/8 − 0.3125 |
| percentages · 150 | 10, 25, 50% of round numbers (50% of 240) | any whole % of a number (answer ≤ 1 dp); % change | chained (up x% then down y%: net %); reverse (after +20% it's 360: original?) |
| desk · 200 | whole-dollar prices $1–9 apart, 100–900 shares: P&L (bought 300 @ 42, sold @ 45 → 900), spread cost, notional (300 @ 40) — every step 1-digit × 1-digit, then zeros | 2-dp prices a multiple of 0.05 apart (up to 0.95), 100–900 shares: P&L round trip (0.25 × 300 = 75), spread cost, notional ≤ 3-digit × 1-digit (400 @ 42.10), VWAP of 2 fills in equal sizes or 2:1 | multi-fill P&L; VWAP of 2–3 fills; P&L with the rest marked |

The lobby's 1–4 keys toggle families on and off (at least one stays on); families are drawn evenly. The difficulty picker (←→) is EASY, MEDIUM, HARD or CUSTOM; CUSTOM opens a screen for the duration (Sprint) or the bonus and its floor (Survival) and, per family, the difficulty and a weight.

**The difficulty ceiling.** Each difficulty's core row is the ceiling for every single step any problem needs, in every family: EASY 2-digit ± and × up to 12×12; MEDIUM 3-digit ± and 2×2 or 3×1-digit ×; HARD 4-digit ± and 3×2-digit ×. Every generator returns its solution steps, a shared check (`within_difficulty`) rejects a problem with any step over the ceiling, and the generator draws again. Decimal points and trailing zeros don't count toward size — 0.25 × 300 counts as 25 × 3.

**Scoring (Sprint, Survival, drill, daily).** Points per correct answer = round(base × combo), where combo = min(1 + 0.1 × streak, 3.0) using the streak from before this answer. A correct answer adds 1 to the streak; a skip resets it. There is no speed bonus. Raw correct and points are shown side by side everywhere.

**Report.** After every run: CORRECT (with skipped and wrong), POINTS (or RAW SCORE / NET) with the best combo, AVG TIME per correct answer, and your LAST 5 RUNS on this mode and difficulty. The WEAKNESS REPORT lists each problem type you saw: seen, right %, average time, your usual (the median time over that type's last 200 correct answers; "—" under 10) and how this run compares ("faster/slower by Xs" from 0.3s, else "same"). The two weakest types (lowest accuracy, then slowest against your usual) are highlighted in red. SLOWEST 3 shows your slowest problems with their answers, and SHORTCUT works the matching tip with the slowest problem's own numbers. Keys: D drill · T all tips · R run again · C copy score card · L lobby.

- **Drill (D):** a 2:00 Sprint on only the run's two weakest types. It's logged but never counts toward your bests.
- **Bests:** per mode and difficulty — Sprint and Survival keep correct and points, Zetamac the raw score, Optiver-style the net. A ★ NEW BEST bar shows when you beat one.
- **Files:** every problem shown goes to `~/.met_games/math_history.jsonl` (date, mode, difficulty, family, type, correct/skipped/wrong, time); run summaries to `math_runs.jsonl`; bests to `math_bests.json`; the daily to `daily.json`.

**Daily challenge.**
- **Seed:** `met-math-daily-YYYY-MM-DD`, from the date in **America/Detroit** whatever your machine's timezone, so the day flips at Detroit midnight. 200 problems are generated, and the run works through them in order.
- **Frozen generator:** the daily's problems come from `met_games/games/math/daily_v1.py`, a self-contained copy of the generator that never imports the main one, so engine changes can't change past or future dailies. The card shows `v1`, and a test pins the first 15 problems of 2026-10-12.
- **Number:** days since `DAILY_EPOCH` (the release date), starting at #1.
- **One attempt (honor system):** starting writes the date to `~/.met_games/daily.json`; after that, D opens today's result instead. The DAILY STREAK counts consecutive days played and shows the time to the next daily.
- **Score card:** C copies it with `pbcopy` (without `pbcopy` the card is shown in a notification instead). Squares are accuracy per family in fifths.

```
MET MATH · daily #N · sprint M · v1
39 ✓ · 5,480 pts · best ×2.2
core ■■■■■   frac ■■■■□
%    ■■■■□   desk ■■■□□
met-games math --daily
```

### Decisions (Math)

- **Answer forms:** "fraction as a decimal" only locks on a decimal and "decimal as a fraction" only on a fraction (any equal fraction, e.g. 6/16 for 3/8); otherwise typing the question back would lock it. Every other problem takes either form.
- **Subtypes per difficulty:** fraction ± fraction is MEDIUM only and fraction ± decimal ("mixed") HARD only; EASY percentages are "% of" only, HARD percentages are chained and reverse only; EASY desk is P&L, spread cost and notional; MEDIUM adds a 2-fill VWAP; HARD desk is P&L (multi-fill or marked) and VWAP.
- **Bounds:** fraction ± fraction uses denominators 2, 4, 5, 8, 10 and 16 (≤ 16 and terminating); results of subtractions and "mixed" problems are positive. Desk lots are 100–900 shares in hundreds on EASY and MEDIUM (HARD: buys of 300–900, VWAP fills of 100–500), prices 10–99 whole dollars on EASY and 10.00–99.99 above. P&L and % change answers can be negative; type `-`.
- **Even mix:** families come out of shuffled bags (each family once per bag, or its Custom weight times), so the mix is exactly even over each bag; the subtype is uniform within a family.
- **Custom:** reached by choosing CUSTOM in the difficulty picker and pressing ⏎ on Sprint or Survival. Weights are 1–5 per family (0 = off); duration steps by 15s.
- **Cut-off problem:** the problem on screen when time runs out (or when you press Ctrl+E) isn't scored or logged.
- **"Your usual":** only correct answers have a time to answer, so the median is over a type's last 200 correct answers, across all difficulties. A run is compared with the history from before it.
- **Survival bonus:** the bonus for a correct answer uses the count before it: on MEDIUM answers 1–10 add 8s, 11–20 add 7.5s, and so on down to 4s (from the 81st). Custom's bonus is 1–20s in 1s steps and its floor 0.5s up to the bonus in 0.5s steps; both start at MEDIUM's 8s / 4s. Without a config (the engine's default) a run uses MEDIUM's.
- **How steps are sized:** a ÷ b = q counts as the multiplication q × b (144 ÷ 12 is 12 × 12). × or ÷ by a power of ten (×100 lots, ÷100 for a percent, 0.1) is a shift, not a step. A ± step counts only the columns it works on: when one number is shorter, only its columns (42.37 + 0.25 is 37 + 25, the carry is an increment), and a subtraction of equal-length numbers skips their shared leading digits (42.62 − 42.37 is 62 − 37). Writing a/b as the answer (`frac`) is not arithmetic. Shared zeros at the end of both numbers don't count either (300 + 500 is 3 + 5).
- **The method in the steps** is the quick one: n/d ↔ decimal is n × (1/d) (3/8 = 3 × 0.125); decimal × integer is n × (k ÷ d) (0.375 × 48 = 3 × 6); fraction ± fraction goes over the common denominator; 10/25/50% is ÷ 10/4/2; VWAP is the low price plus the weighted offsets.
- **What the ceiling removed:** EASY no longer asks 3/4 ↔ 0.75 (3 × 0.25 is past 12×12; 1/4 ↔ 0.25 stays), and EASY halving and quartering stay within the 12× table (0.5 × 18, 50% of 240, not 0.5 × 66). MEDIUM drops % of with a 2-digit % of a 3-significant-digit number (55% of 874) and % changes that need more than 2×2 or 3×1. HARD reverse % drops originals with 4 significant digits (after +25% it's 2063.75). MEDIUM desk drops prices that cross a dollar with no digit in common (49.90 → 50.85). The subtype mix within a family is unchanged: a redraw keeps the subtype.
- **Desk subtypes by difficulty:** EASY now has spread cost and notional too (with its own limits); MEDIUM adds the 2-fill VWAP. MEDIUM spread cost uses the same price-difference rule as P&L (a multiple of 0.05 up to 0.95). EASY notional prices are a single digit and zeros (1–9 or 10–90) so the step is 1-digit × 1-digit.
- **Steps live on each problem** (`Problem.steps`, a tuple of (op, a, b)); the frozen daily generator is untouched, so daily problems carry none and aren't re-checked.
- **Zetamac:** Tab skips there too (no combo to reset). Zetamac and Optiver-style are fixed formats, filed under the difficulty `standard`; the difficulty picker and mix toggles don't apply to them.
- **Optiver-style:** families come in shuffled bags of (decimals & fractions, percentages, core), each question at MEDIUM or HARD at random.
- **Bests:** the first non-zero result on a board counts as a NEW BEST. Correct and points (Sprint, Survival) are tracked separately.
- **Drill:** each weak type is drilled at the difficulty it was seen at (Zetamac's arithmetic at MEDIUM); R on a drill's report runs another drill on the same types.
- **Score card for other runs:** C on any report copies a card in the same shape, with the run's seed and the command that replays it. The daily's squares round half up (90% is five squares); a family with no problems shows five empty squares.
- **No pbcopy:** the app owns the terminal while it runs, so instead of printing the card it shows it in a notification for 20 seconds (it's also on the daily screen).
- **R on the daily's report** does nothing (one attempt). Ctrl+E, or leaving from the pause menu, ends the daily and saves what you scored.
- **Data files:** besides `math_history.jsonl` and `daily.json`, run summaries (`math_runs.jsonl`) and bests (`math_bests.json`) get their own files.
- **Timezone data:** the Detroit date uses the standard library's `zoneinfo` (the system's tz database); no new dependency.
- **CLI:** `--mode` starts that run from the math lobby (L returns to it), `--difficulty` preselects the difficulty, `--daily` opens the daily (and implies `math`). The `--help` column is capped so the existing help text wraps as before.
- **Existing tests:** the only changes are the list-of-games assertions, which now include MATH.
