# MET Games — Michigan Electronic Trading

Solo trading and mental-math drills for **MET (Michigan Electronic Trading)**, played in your terminal.

`met-games` is a [Textual](https://textual.textualize.io/) app containing seven games that practise the skills tested in trading interviews and used on a desk. These are pricing under uncertainty, making and taking markets, reacting to a live order book, arbitrage, bet sizing, and fast exact arithmetic. Every game is seeded, so a club can play identical sessions and compare results.

## The games

| game | CLI key | home-screen tagline | what you practise |
|---|---|---|---|
| **Card Game** | `card` | Card Expected Value | Taking a market on the sum of dealt cards (whole-dollar prices) |
| **Dice Game** | `dice` | Smaller Tick Sizing | The same drill on dice, with prices in 0.25 ticks |
| **Trading Game** | `trade` | You vs. 3-4 Traders | Making two-way markets and trading other players' markets on one deal |
| **Outcry** | `outcry` | 8-Player Open Outcry | Open outcry in a live order book on a contract that settles at a hidden sum |
| **ETF Arb** | `etf` | Basket Arbitrage Race | Pricing a basket's NAV and racing to arb the ETF quote |
| **Hi/Lo** | `hilo` | Kelly Sizing Speed Run | Calling the next card and sizing each bet by the Kelly criterion |
| **Math** | `math` | Mental Math Sprints | Exact mental arithmetic, estimation, probability and desk math |

Each game has a lobby with EASY / MEDIUM / HARD presets (most also offer CUSTOM), a how-to screen that gives the full rules, a recap or report at the end of a session, and a stats screen that draws on your saved history.

### Card Game and Dice Game

Some cards or dice are dealt face up and the rest are hidden. A market maker quotes a two-way price on the sum of all of them, and you buy, sell, or pass before the timer runs out. Market events can change the rules before the quote, for example face cards count 10, aces count 1, red cards count negative, or one hidden card counts double. After the reveal you report your own P&L. The game then grades your decision on **edge** (was it a good trade at the time?) separately from **luck** (how the draw went). Both games share the `sumgame` core, so they differ only in item type, tick size and events.

### Trading Game

You and three computer traders (DELTA, GAMMA, THETA) sit at a table and play one deal of cards per hand. On turn *i* the player in seat *i* makes a market, and the other three may trade it. Positions and cash carry across the four turns. After turn 4, every position settles at the sum of the cards, so the four hand P&Ls always sum to zero. The deal follows the Card Game's rules (values, events and fair value).

### Outcry

You and seven computer traders each hold one hidden whole number drawn from a hidden range. One contract settles at the sum of all eight numbers. Each round has a forced open quote, a blind forced response, a timed open outcry in a live price-time order book, and then one anonymous reveal. The lowest and highest numbers are revealed at fixed points with labels. The computer traders use hidden styles (MAKER, SNIPER, PASSIVE, CHASER, ANCHOR), and each prices from its own exact conditional fair value. At the end you score your own trades, and then the owners, the true range and the leaderboard are revealed.

### ETF Arb

Each round shows a basket of stocks with fixed weights, a set of price moves, and an ETF bid/ask posted near NAV = Σ weight × price. You work out the NAV and then buy at the ask, sell at the bid, or skip. Three computer traders (KESTREL, OSPREY, MERLIN) race you for the same limited size. Every trade pays a flat fee, and the first profitable trade of the round earns a bonus. Some rounds the gap is too small to be worth trading.

### Hi/Lo

A card is showing. You call whether the next one is higher or lower (or, with the Red/Black deck, which colour it is), and you stake a whole percent of your capital at even money. Each bet is graded against the Kelly stake k = |h − l| ÷ (h + l), with combo multipliers and an optional speed bonus. A capital bonus is added at the end, and your result is compared with a Kelly benchmark run on the same deck order. The decks are Interview (13 cards), Full (52) and Red/Black.

### Mental Math

These are exact-answer drills, grouped in the lobby as follows:

- **ARCADE**: Sprint, Survival, Chain and Estimate.
- **TEST DRILLS**: Zetamac, Optiver-style, Flow-style 60/6 and a Probability drill.
- **MORE**: the daily challenge, My Stats and Settings.

Adaptive difficulty tracks your level separately on seven skill tracks. Reports point out your weakest areas and offer a targeted drill. See the [Mental Math reference](#mental-math-reference) below.

## Install

### Homebrew (macOS and Linux)

```bash
brew install MichiganElectronicTrading/tap/met-games
met-games
```

To update to the latest release:

```bash
brew upgrade met-games
```

`met-games --version` prints the installed version.

### uv (development, or without Homebrew)

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv run met-games            # run from a clone of the repo (creates the venv on first run)
# or install it as a tool:
uv tool install .
met-games
```

`python -m met_games` also works inside the venv.

## Run

The app opens on the **MET GAMES** home screen, which lists every game plus SETTINGS and QUIT. Press ⏎ on a game to open its lobby. You can also go straight to a lobby:

```bash
met-games card                 # or: dice, trade, outcry, etf, hilo, math
met-games dice --seed 42       # every session this run uses seed 42
met-games hilo --deck redblack # Hi/Lo: start on a given deck (interview, full, redblack)
met-games math --mode chain    # Math: start a mode straight away (see the Mental Math reference)
met-games math --daily         # Math: today's daily challenge
met-games --help
```

## Club play

To run a head-to-head drill, pick a seed and have everyone run the same command:

```bash
met-games card --seed 1234      # works for any game: dice, trade, outcry, etf, hilo, ...
```

Everyone must also pick the same game and mode. With the same seed, everyone gets identical deals, events, flips, quotes and computer-trader behaviour, so the only differences are the decisions people make. When the session ends, compare recaps; each one shows `SEED 1234` in its top bar. In Card, Dice and Trading, FINAL BALANCE shows who made the most money, but EDGE TAKEN is the fairer score, since LUCK is the same draw for everyone. Pressing R on the recap replays the seed for a rematch.

## Your data

History, bests, adaptive levels and settings are saved under `~/.met_games/`. To use a different folder, set `MET_GAMES_HOME`. Each game writes its own files, for example `card_history.jsonl`, `hilo_scores.json`, `math_levels.json` and `settings.json`. In Card, Dice, Trading, Outcry and ETF Arb, the stats screen's CLEAR STATS button deletes that game's history only, after asking you to confirm.

## Settings

**SETTINGS** opens from the home menu (above QUIT) and from the Mental Math lobby (MORE ▸ SETTINGS, or the `,` key). Esc goes back to wherever you came from. Keys: ↑↓ pick a setting · ←→ change its value · R reset this section to NORMAL · Esc back. Every change is saved at once to `~/.met_games/settings.json` (respects `MET_GAMES_HOME`), one namespace per game: `{"math": {"problem_size": "normal", "answer_size": "normal"}}`. A missing or unreadable file reads as all defaults and is rewritten on the next change. Keys from other games are kept. The screen is built from a list of sections, each with its own typed options, so other games can add theirs.

### Mental Math · Display

| size | rows | look |
|---|---|---|
| NORMAL (default) | 1 | plain text — exactly what the screens always drew |
| LARGE | 3 | line digits (Textual's bold 3×3 digits, plus / ÷ % , . − = ? and space) |
| HUGE | 5 | block digits (█ ▀ ▄), about 4 columns each |

- **PROBLEM SIZE** applies to the main problem in Sprint, Survival, Zetamac, Optiver-style, Chain, Estimate, Flow-style, the daily and drills. In Chain on EASY and MEDIUM, the carry keeps its amber.
- **ANSWER SIZE** applies to the typed answer line (with a cursor) and the four Optiver-style choice boxes. The boxes grow taller to fit; their number badge stays normal size.
- Side panels, logs, headers and reports always stay normal size.

**Fallback rules.**
- **Word problems:** desk, probability, counting, "% of", √, and anything with a letter or symbol the big fonts don't have stay NORMAL, with no message.
- **Problems:** if a problem is wider than its panel, it drops one size at a time (HUGE → LARGE → NORMAL). It is rechecked on every redraw, so on resize too.
- **Choice boxes:** each Optiver-style box falls back on its own.
- **Answer line:** it uses the biggest size that fits as you type, so a long answer shrinks rather than clipping.
- **Input is unchanged:** big digits are drawing only. Auto-lock, Enter, timing and parsing all use the raw typed text.

## Mental Math reference

```bash
met-games math --mode chain                            # also: estimate, sprint, survival, zetamac, optiver, flow, prob
met-games math --mode sprint --difficulty adaptive     # adaptive is for sprint, survival and prob
```

The lobby has three sections. **ARCADE** holds Sprint, Survival, Chain and Estimate. **TEST DRILLS** holds Zetamac, Optiver-style, Flow-style and the Probability drill. **MORE** holds the daily, My Stats and Quit. Every entry is live. The difficulty pills show only what the selected mode supports. **S** opens My Stats.

### Adaptive: tracks and levels

Every problem type belongs to one of seven skill tracks. The map lives in `ladder.SUBTYPE_TRACK`:

| track | subtypes | target time |
|---|---|---|
| addsub | add, sub | 2.5s |
| mul | mul | 3s |
| div | div | 3.5s |
| dec | decimal → fraction, decimal × integer | 4.5s |
| frac | fraction → decimal, fraction ± fraction, fraction ± decimal | 5s |
| pct | % of, % change, chained %, reverse % | 5s |
| desk | P&L, spread, notional, VWAP | 8s |

Each track has its own level from 1 to 10. L3, L6 and L9 are the EASY, MEDIUM and HARD generators, and they produce exactly the same draws. L1–2 are easier than EASY and L10 is harder than HARD. The rungs in between step up operand sizes and digit counts, and each one stays within the next anchor's step limit.

The rule works per track, within a run:

- **Up one level** after 3 correct answers in a row, each within the target time.
- **Down one level** after a miss or skip, or after 2 correct answers in a row that are slower than twice the target.
- Any level change resets both counters.

Levels are saved in `~/.met_games/math_levels.json`, with one snapshot per day kept for 60 days. The first time a track is used, it starts at the highest anchor (L3, L6 or L9) where you have at least 80% accuracy over at least 20 logged problems at that difficulty. Otherwise it starts at L3.

Adaptive Sprint and Survival keep their own bests (`sprint/adaptive`, `survival/adaptive`). Adaptive Survival uses MEDIUM's clock. The daily never uses Adaptive.

### Chain

A chain starts from a random number. Each link applies one operation to the carry, and your answer becomes the new carry. Type the answer and press Enter; nothing locks automatically. A wrong answer, or running out of time on the step clock, ends the chain. The step clock stops while the pause menu is open.

| | carry | step clock | operations |
|---|---|---|---|
| EASY | ≤ 3 digits | 15s | ± 1–2 digits, × 2–9, exact ÷ 2–9 |
| MEDIUM | ≤ 4 digits | 12s | adds × and ÷ up to 12, and ± 10/20/25/50% when the result is whole |
| HARD | ≤ 4 digits | 10s | × and ÷ up to 19, any whole % with a whole result; the carry and log hide after your first answer |

The carry is always a positive whole number. If an operation would break that, the generator draws a new one rather than clamping the result.

- **Points:** each link scores round(base × combo). The base is 100, or 150 for a % link, and combo = min(1 + 0.1 × links so far, 3).
- **Bests:** longest chain and points, per difficulty.
- **Custom:** a step clock of 5–20s, plus on/off toggles for ×, ÷ and %.
- **Report:** length, points, average step time, your last 5 runs, the full chain log, and a BROKE AT panel with the tip for that link's track.
- **History:** each link is logged with mode `chain` and its track (± → addsub, × → mul, ÷ → div, % → pct).

### Estimate scoring

Estimate is 15 questions with 15 seconds each: three each of big ×, ÷ by a decimal, x% of y, √ of a non-square, and a 4-digit number × 0.0xxx. Type a number (commas are ignored) and press Enter. The exact answers are computed with `Decimal`, with ÷ and √ rounded to 8 places, and they are never round numbers.

- Your answer is scored on off = |guess − exact| / |exact|:
  - within 1%: 100 (FULL)
  - within 5%: 50 (HALF)
  - within 10%: 25 (QUARTER)
  - otherwise 0 (MISS)

  Each limit counts as inside its band.
- Answering within 4s doubles the points, and within 8s multiplies them by 1.5. A timeout scores 0, and there is no combo.
- **Bests:** points, per difficulty.
- **History:** logged as family `est`, which stays out of the skill tracks.

### My Stats

←→ picks the mode and ↑↓ picks the difficulty. The top bar shows your total runs, the date of your first run, and your daily streak.

- **Last 20 runs:** a ▁–█ sparkline scaled to its own minimum and maximum, followed by first → median → latest. The stat shown is correct answers for Sprint, Survival and Zetamac, net for Optiver-style, length for Chain, and points for Estimate.
- **Median time per family:** your first 10 runs against your last 10, across all modes. It shows "—" until you have 20 runs.
- **Adaptive levels:** every track's level, with ▲ ▼ · against the snapshot from 7 days ago.
- **Bests:** each mode at the hardest difficulty where you have a best, with its date.
- **Focus next:** the track with the biggest 7-day level drop. If nothing dropped, it is the track with the lowest accuracy over your last 100 problems. **F** starts a 2:00 adaptive Sprint on that track only. It is logged and moves your levels, but never counts toward bests.

### Flow-style 60/6 (unofficial practice format)

Flow-style is an unofficial practice format, not any firm's real test, and it makes no claims about real cutoffs.

- **Format:** 60 questions in 6:00, mixing core arithmetic with decimals and fractions at MEDIUM–HARD.
- **Answering:** type the answer and press Enter; nothing locks automatically. An empty Enter skips. A wrong answer still moves on, and there's no going back.
- **No feedback until the end:** the header shows how many you've answered, but ✓, ✗ and SCORE stay hidden ("?") until the report.
- **Pace panel:** your seconds per question against the pace you need (time left ÷ questions left). It's green when you're at or under that pace, red otherwise.
- **Pausing:** Esc hides the board, but the clock keeps running, as in a real test.
- **Score and bests:** the score is the number correct, and the best is your highest correct count.
- **Report:** all 60 rows (question, your answer, the right answer and your time), with wrong answers highlighted. Below them come the usual weakness report, slowest 3 and shortcut.

### Probability drill and the `prob` family

The drill is 20 questions in 10:00. Type an answer and press Enter, or press S to skip. Right after each answer you see ✓, or ✗ with the right answer. A WHY panel shows that problem's explanation until your next answer, plus a note when your wrong answer matches a known mistake. The difficulties are EASY, MEDIUM, HARD and ADAPTIVE. Bests are the number correct per difficulty. The report shows your score, accuracy per subtype, and every miss with its explanation.

`prob` is a problem family worth 200 base points. It appears only in this drill, never in Sprint, Survival, Chain or the daily.

| | EASY | MEDIUM | HARD |
|---|---|---|---|
| dice | one die | two dice: sums, doubles, higher/lower die, at least one X in 2 rolls | at least one X in up to 4 rolls |
| cards (counting) | 2-card hands, ordered 2-card draws, both hearts, both aces, one heart and one spade | all 5-card hands, 3 cards with exactly one ace, 3 cards of one suit, 5 cards of one suit, 5 cards with no aces, ordered 3-card draws | full house, four of a kind, two pair, exactly one pair, three of a kind (no full house), at least one ace, exactly two suits, five different ranks |
| coins | all heads in ≤ 3 flips | exactly k / at least one, n ≤ 4 | n ≤ 6, plus runs ("3 or more heads in a row") |
| ev | coin and card bets | E of a die, a die × $m | E of the higher/lower of two dice, E of face², pay-to-play games, fair prices |
| cond | — | — | "given at least one 6, P(both 6)", coins, cards |

**Card questions are counting questions.** Every card question asks "How many …" and wants a whole number of ways. The wording always says whether order matters ("order doesn't matter" for a hand, "order matters" for a draw). It spells out what counts instead of using a poker name with hidden exclusions, e.g. "all five the same suit (straight flushes included)". The rank, suit, number of cards (2–3) and "exactly k" vs "at least one" are drawn at random. Type a whole number, with or without commas ("2,598,960"). Fractions, decimals and the decimal tolerance below don't apply. The SO FAR log and the report print counts with thousands separators. Their subtype is `cards_count`. Before this change it was `cards`, and those were probability questions; old history lines keep `cards`, so the two never mix in the stats.

**Answer tolerance.** Every other answer is a reduced fraction. A fraction is accepted in any equivalent form (2/12 for 1/6). A decimal is accepted when it is exactly equal ("0.75" for 3/4), or when it has at least 3 decimal places and is within 0.0005 of the exact answer ("0.167" for 1/6, but not "0.17"). This is the only tolerance in Mental Math, and it lives in one function, `prob.close_enough`.

**Explanations and mistakes.** Every problem carries a 2–3 line explanation built from its own numbers (for example "13 × C(4,3) × 12 × C(4,2) = 13 × 4 × 12 × 6 = 3,744" or "C(52,5) − C(48,5) = 2,598,960 − 1,712,304 = 886,656"). Known wrong answers are recognised and explained in one line:

- adding P(at least one) roll by roll instead of 1 − P(none);
- a missing order count for coins (C(n, k));
- an off-by-one dice sum (the count for s ± 1);
- counting: ordered vs unordered (the answer × k!, or ÷ k! for draws in order);
- counting: two pair with 13 × 12 rank orderings instead of C(13,2) (2× the answer);
- counting: "at least one ace" as 4 × C(51,4);
- counting: one pair with C(48,3) for the other three cards, which lets them pair up;
- counting: three of a kind that includes the 3,744 full houses.

**Adaptive.** `prob` has its own ten-level track. L3, L6 and L9 are EASY, MEDIUM and HARD; L1–2 are easier and L10 adds 3-dice sums, up to 8 coins, E of the highest of 3 dice and more conditional problems. It uses the same up/down rule as the other tracks, with a 15s target.

### Design notes

- **The dec / frac split:** the decimals-and-fractions subtypes are divided by what you start from. Decimal → fraction and decimal × integer are `dec`; fraction → decimal, fraction ± fraction and fraction ± decimal are `frac`. This puts subtypes on both tracks at every anchor.
- **Track choice:** an adaptive run picks families from the same shuffled bags as Sprint, then picks one of that family's tracks evenly. So addsub gets a third of core, not half.
- **Operand size:** "operand size" means the most significant digits of any number in the problem text (0.375 → 3, 300 → 1). Each track declares that reach per level (`ladder.DIGITS`). The reach never goes down, and the anchor levels match exactly what today's generators reach.
- **Edge cases of the rule:**
  - An answer slower than the target but within twice the target breaks both runs.
  - At L1 or L10 a firing rule changes nothing, but it still resets the counters.
  - A track missing from the levels file is seeded once and saved, so later history doesn't move it.
- **7-day comparison:** arrows compare against the latest snapshot at least 7 days old. Until one exists, they compare against the oldest snapshot.
- **Weakness drill:** D on a report drills an adaptive problem at its nearest anchor (L1–4 EASY, L5–7 MEDIUM, L8–10 HARD).
- **Chain start number:** 10–99 on EASY, 10–999 on MEDIUM and HARD.
- **Chain % links:** a % link reads "480 + 25%". Its tip covers the p% of the carry, then adds or subtracts it.
- **Chain Custom:** Custom uses MEDIUM's limits. ± is always on, because without it a chain could run out of valid moves (for example, a prime carry with only ÷ left).
- **Chain timeouts:** a timeout is logged as outcome `timeout`. In the run summary it is the "skipped" count.
- **Estimate difficulty:** Estimate has no Custom; its pills are EASY, MEDIUM and HARD.
- **Estimate operands:** "digits" means significant digits.
  - EASY: 3-digit × 2-digit whole numbers.
  - MEDIUM: 4 significant digits with 1 decimal place (482.7).
  - HARD: 4–5 significant digits with 2–3 places (48.217), with √ of 5-digit numbers.
  - The × 0.0xxx kind always uses a 4-digit number in that difficulty's style.
- **Estimate answers:** exact answers are at least 1, and "round" means fewer than 3 significant digits.
- **Half points:** 25 × 1.5 gives half points (37.5). They are kept exactly and stored as JSON numbers, which hold halves exactly.
- **Sparkline:** if every value is equal, it draws a flat middle line (▄).
- **Bests panel:** "best difficulty" means the hardest one with a best on file, in the order HARD, MEDIUM, EASY, ADAPTIVE, CUSTOM.
- **Median-time panel:** it covers the four problem families; Estimate's lines aren't included.
- **Report keys:** L on any report now goes to the math lobby, even when the run started from My Stats.
- **Prob outside FAMILIES:** `prob` stays out of `FAMILIES` and the v2a track list, so Sprint's mix toggles, the daily and Sprint/Survival adaptive runs can never draw it. The prob level is saved in the same `math_levels.json`, and saving one set of levels leaves the others alone. My Stats lists it with the other levels, but Focus next only names Sprint/Survival tracks, since F starts a Sprint-style drill.
- **Prob target time:** 15s per question, which is "fast" for the up rule.
- **Prob ladder:** in the prob ladder, a problem's level and kind fix its setup ("2 cards from 52"). The tests check every answer by brute force over real dice, coin sequences and a 52-card deck, never the generator's formula.
- **EASY coins:** "one coin" means one coin flipped 2–3 times (all heads). A single flip would always be 1/2.
- **Prob subtypes:** conditional probability appears only at HARD (L9) and above. HARD contains every subtype.
- **Mistake matching:** a known mistake is matched with the same tolerance as answers, so "0.006" is recognised as (1/13)² = 0.00592 with replacement. A "mistake" that happens to equal the right answer is dropped for that problem.
- **Flow-style problems:** Flow-style draws core and decfrac problems from alternating shuffled bags, each at MEDIUM or HARD at random, so there are 30 of each. Answers are checked exactly, using the same rules as the arcade modes.
- **Flow-style header:** ✓, ✗ and SCORE show as "?" during the run. The spec asks for them in the header but also asks for no feedback until the end.
- **Flow-style leaving:** pausing doesn't stop the clock. Leaving from the menu abandons the test, like any other mode.
- **Probability drill input:** an Enter on text that isn't a number yet (like "1/") does nothing, and S is the only way to skip.
- **Lobby navigation:** with Flow-style and Probability drill live, ↓ from Survival now stops on every mode.
- **Counting answers:** a counting answer must be a plain whole number. Commas are allowed only between groups of three ("1,326", not "13,26"). Anything else ("1326.0", "1/1") does nothing on Enter, the same as a half-typed fraction; S skips.
- **One-pair detector:** the spec's one-pair mistake ("forgetting that the 3 kickers have different ranks") is the count 13 × C(4,2) × C(48,3) = 1,349,088. C(12,3) × 4³ is the right kicker term, so the detector fires on the C(48,3) version.
- **Card ladder:** L1–2 hold the 2-card hand questions. L4–5 add 2–3-card counts, with 5-card hands from L5. L7–8 move into 5-card hands (four of a kind, five different ranks, at least one of a rank, full house, three of a kind). L10 adds "exactly 3 of a rank".
- **Brute-force tests:** the 5-card tests enumerate all 2,598,960 hands once and count rank-specific and suit-specific cases for aces and hearts. Every rank and suit gives the same count by symmetry.
- **Desk question wording:** every desk question ends by naming the quantity it wants, and that quantity's sign rule. No question asks for a "cost", "loss" or "profit". Two prices quoted against each other are always labelled bid and ask. Answers are checked exactly, sign included: "200" never locks a −200 answer.

  | subtype | template | sign |
  |---|---|---|
  | pnl (round trip) | `bought 300 @ 42.10, sold 300 @ 42.35 · P&L = ?` | signed: + gain, − loss |
  | pnl (multi-fill) | `bought 500 @ 42.15, sold 200 @ 42.40 and 300 @ 42.05 · P&L = ?` | signed |
  | pnl (marked) | `bought 500 @ 42.15, sold 300 @ 42.40, rest marked @ 42.30 · P&L = ?` | signed; the unsold lots count at the mark |
  | spread | `bid 91.18 / ask 91.68 · buy 400 at the ask, sell at the bid · P&L = ?` | always negative: (bid − ask) × qty = −200 |
  | notional | `buy 300 @ 42.10 · notional = ?` | always positive |
  | vwap | `fills 200 @ 42.10, 300 @ 42.20 · VWAP = ?` | always positive |

  On the keyboard the minus sign is "-". The daily keeps its frozen v1 wording (`daily_v1.py` is never edited, so the daily numbers and their snapshot test don't change). That includes the old positive "cost" spread question, but only inside the daily.
- **Settings screen layout:** the preview always shows NORMAL text for word problems, matching the game. The PREVIEW and side panels come from each section, so another game's section brings its own.
- **Big problem text:** the big problem includes its " =" (Estimate shows no "≈" when big, since the badge line already says it). An Optiver-style question renders with " = ?". The NORMAL drawing is byte-for-byte what the screens drew before; `tests/snapshots/math_normal_screens.json` was recorded from the earlier code, and a test compares every run screen against it.
- **Answer cursor:** the big answer line ends in a "▌" cursor. NORMAL has never shown one, so it still doesn't.
- **NORMAL with other characters:** `render(text, NORMAL)` returns the text unchanged, even with letters. Only LARGE and HUGE return None for characters they can't draw.
- **Glyph widths:** at LARGE, "." and "," are one column wide and a space is one column. At HUGE they are two columns wide.
- **Settings timing:** settings are read when a run starts, so a change applies from the next run.
- **Corrupt settings:** a settings file that isn't a JSON object (a list, broken JSON, non-UTF-8) reads as all defaults. A game section that isn't an object is replaced on the next save.

## Development

```bash
uv run pytest                  # full test suite
```

The engines contain no Textual code. They run on a 0.25 s tick counter instead of the wall clock, so the tests can drive whole games instantly and replay seeds exactly. `tests/test_seed_pins.py` pins seeded deals so they can't drift, and `tests/snapshots/` holds recorded screens for the Mental Math NORMAL display.

```
met_games/
  __main__.py          CLI entry point (met-games, plus the legacy mtt-games alias)
  app.py               home screen and the GAMES registry
  settings.py          settings storage; settings_screen.py draws the Settings screen
  storage.py           ~/.met_games paths and the mtt → met migration
  bigtext.py           LARGE / HUGE digit rendering
  widgets.py, pause.py, theme.tcss   shared UI pieces
  games/
    sumgame/           shared core for Card, Dice and Trading (lobby, rounds, recap, stats)
    card/ dice/ trade/ the sum games
    outcry/ etf/ hilo/ engine + model + computer traders + screens
    math/              problem generators, adaptive ladder, modes, daily, screens
tests/
```

To add a game, create a new package under `met_games/games/` and add one `GameInfo` line to `GAMES` in `met_games/app.py`. If the game has settings, add a section to `SETTINGS_SECTIONS`.

## Releasing

The version is set only in `pyproject.toml`. `met_games.__version__` and `met-games --version` read it from the installed package.

1. Set `version` in `pyproject.toml`, then run `uv sync`.
2. Run `uv run pytest`; every test must pass. `tests/test_packaging.py` checks the version, `--version`, and that nothing writes inside the install directory.
3. Run `rm -rf dist && uv build` to build `dist/met_games-X.Y.Z.tar.gz` and the wheel.
4. Check the sdist without uv. In a fresh venv, run `python3 -m venv /tmp/met-check && /tmp/met-check/bin/pip install dist/*.tar.gz && /tmp/met-check/bin/met-games --version`. It must print `met-games X.Y.Z`.
5. Tag `vX.Y.Z`, push the tag, and create a GitHub release with the sdist attached.
6. In the `MichiganElectronicTrading/homebrew-tap` formula, update `url` to the new sdist and `sha256` to the output of `shasum -a 256 dist/met_games-X.Y.Z.tar.gz`. Then check it with `brew upgrade met-games && met-games --version`.

## Upgrading from mtt-games

This project used to be **mtt-games**, for MTT (Michigan Trading and Technology). It is now **met-games**, for MET (Michigan Electronic Trading). Seeds are unchanged, so `--seed N` deals the same game as before. On first run, your history is copied from `~/.mtt_games` to `~/.met_games`; the old folder is left in place. `MTT_GAMES_HOME` still works if `MET_GAMES_HOME` is unset. The `mtt-games` command still works for now, but it prints a notice and will be removed in a future version. To swap the installed command:

```bash
uv tool uninstall mtt-games
uv tool install --force --editable .
```
