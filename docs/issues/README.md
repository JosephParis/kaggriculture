# Kaggriculture backlog

**Deadline: 30 September 2026, 23:59.** $50,000 pool, $5,000 to each of the top
10. 4,850 teams entered as of 16 August.

## What the game actually is

A **two-player** farming sim over 720 turns (24 turns/day × 30 days). Most coins
banked at the end wins; unsold inventory counts for nothing. The agent is a
plain function — observation in, action dict out — so this is a policy problem,
not a model-training one. There is no dataset.

Three facts shape almost every decision:

- **The market is shared and price-responsive.** Sale price falls as market
  inventory rises. Premium goods (strawberry, melon, milk, wool) collapse toward
  the $1 floor on a glut; staples absorb supply more gently. So the opponent
  selling wheat hurts *your* wheat price. Production strategy and sell timing
  are the same problem.
- **Both farms are public.** `obs["farms"]` carries the opponent's tiles, money,
  and position. Only their shed, seeds, and carried inventory are hidden. The
  opponent is observable, which makes reacting to them legitimate and cheap.
- **Everything must be maintained daily.** Plants unwatered two days running
  become weeds; animals unfed two days escape permanently. Labour is the real
  constraint, and each unit gets exactly one action per turn.

## Economics worth memorising

| | Seed | Base price | First yield | Units/tile/day |
|---|---|---|---|---|
| Wheat | 10 | 25 | day 2 | **0.80** |
| Carrot | 20 | 35 | day 2 | 0.75 |
| Melon | 80 | **250** | day 10 | 0.55 |
| Tomato | 50 | 60 | day 8 | 0.33 |
| Strawberry | 100 | 120 | day 10 | 0.24 |
| Goose (eggs) | 300 | 50 | day 4 | **1.00** |
| Cow (milk) | 400 | 160 | day 8 | 0.50 |
| Sheep (wool) | 500 | 200 | day 6 | 0.33 |

Wheat is the fastest cycle **and** the only animal feed, so a wheat engine is a
prerequisite for livestock. Melon is the premium play but ties a tile up for ten
days. Geese have the best raw rate but cost 300 plus a coop.

Starting bank is $3,000. Land: NW free, then $1k / $2k / $4k.

## Working rules

- **Never submit from an unattended run.** Submissions are rate-limited and
  cannot be withdrawn. `eval.py` measures locally; a human submits.
- **Never report a single game.** Weeds, shop unlocks and market noise make one
  result meaningless. Always a win rate over a batch, with the spread.
- Baseline to beat is whatever `main.py` currently scores against `starter`.
  Record it in the issue when it moves.
- Environment: **`py -3.12`**. The default `python` is a sandboxed Store 3.9 and
  `kaggle-environments` requires ≥3.11.

## The backlog

### P0 — can't do anything without these

| # | Issue | Effort | Status |
|---|---|---|---|
| [01](01-baseline-and-harness.md) | Baseline agent and local eval harness | M | **done** |
| [02](02-measure-the-market.md) | Measure the price function empirically | M | open |

**Current baseline: 100% vs `starter` over 20 games, median $6,024 (theirs
$3,560).** Beat that number or it is a regression. `py eval.py --games 20`.

Labour is confirmed as the binding constraint, not land or money. The first
baseline planted 15 tiles, could not water them, and the farm was weeds by day
6 — final profit $46. Sizing the plot to the workforce took it to $3,024 profit
with no other change. Every later decision (hiring, land, animals) is really a
question about labour capacity.

### P1 — the actual game

| # | Issue | Effort | Status |
|---|---|---|---|
| [03](03-labour-scheduling.md) | Labour scheduling: the real constraint | L | open |
| 04 | Crop mix: when melon beats wheat | M | open |
| 05 | Hiring policy against the fibonacci cost curve | M | open |
| 06 | Land expansion: when $1k/$2k/$4k pays back | M | open |

### P2 — compounding advantages

| # | Issue | Effort | Status |
|---|---|---|---|
| 07 | Livestock: feed economics and the wheat dependency | L | open |
| 08 | Town shop demand: track unlocks, sell into them | M | open |
| 09 | Opponent modelling: both farms are visible | L | open |
| 10 | Sell timing against the shared market | M | open |

### P3 — operational

| # | Issue | Effort | Status |
|---|---|---|---|
| 11 | Submission pipeline and leaderboard tracking | S | open |
| 12 | Replay analysis tooling | M | open |

## Dependencies

```
01 (harness) ──> everything: nothing can be measured without it
02 (market)  ──> 04, 10  (crop mix and sell timing are both price problems)
03 (labour)  ──> 05, 06, 07  (hiring, land and animals all buy labour or need it)
07 (animals) <── wheat engine from 03/04
```

## If you only do three

**01**, **02**, **03**. The harness makes everything else measurable, the market
determines whether producing more is even good, and labour scheduling is the
constraint every other decision runs into.
