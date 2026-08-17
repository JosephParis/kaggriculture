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

Reprioritised 17 August 2026 — see [STRATEGY.md](../STRATEGY.md) for the
reasoning. Two things changed everything: the environment source is readable on
this machine, so mechanics never need probing; and hiring 2–4 hands nearly
doubles the baseline for $7/day, so the engine is much further from optimal than
the ordering below assumed.

### P0 — the engine

| # | Issue | Effort | Status |
|---|---|---|---|
| [01](01-baseline-and-harness.md) | Baseline agent and local eval harness | M | **done** |
| [02](02-measure-the-market.md) | Measure the price function empirically | M | **closed — answered from source** |
| 13 | Parameter sweep harness over batched games | M | open |
| 05+06 | Hire-and-expand: hands and land scale together | M | open |
| 07 | Livestock: the goose/egg/fertilizer engine | L | open |
| 04 | Crop mix: wheat for feed, melon for the premium slice | M | open |

**Current baseline: 100% vs `starter`, median $6,024 over 20 games (theirs
$3,560).** Beat that number or it is a regression. `py eval.py --games 20`.

**Measured ceiling on the labour lever:** the same baseline with `HIRE` bolted on
and `PLOT` widened to the whole NW quadrant scores a median $10,878 at 4 hands
(4 games). The strategy doc estimates $30k–50k is reachable with livestock. The
gap between $6k and $30k is engine, not tuning.

Labour was confirmed as the binding constraint early: the first baseline planted
15 tiles, could not water them, and the farm was weeds by day 6 — final profit
$46. Sizing the plot to the workforce took it to $3,024 profit with no other
change. The correction to that lesson is that the answer was never "plant less",
it was "hire more and buy land".

### P1 — making the engine sharp

| # | Issue | Effort | Status |
|---|---|---|---|
| [03](03-labour-scheduling.md) | Labour scheduling: assignment across many units | L | open |
| 10 | Sell timing: dump `log` goods, meter `linear`/`sq` goods | M | open |
| 14 | Endgame: liquidate by day 29, unsold inventory scores zero | S | open |

### P2 — margins

| # | Issue | Effort | Status |
|---|---|---|---|
| 08 | Town shop demand: track unlocks, sell into scarcity | M | open |
| 11 | Submission pipeline and leaderboard tracking | S | open |
| 12 | Replay analysis tooling | M | open |

### P3 — probably not worth it yet

| # | Issue | Effort | Status |
|---|---|---|---|
| 09 | Opponent modelling: both farms are visible | L | open |

Demoted. With an order of magnitude between us and our own baseline, reacting to
the opponent is premature. The one opponent-aware behaviour that pays now is the
fertilizer and melon race, and that reduces to "sell premium goods early" — it
needs no model.

## Dependencies

```
01 (harness) ──> everything: nothing can be measured without it
13 (sweeps)  ──> 04, 05+06, 07, 10  (every policy constant wants tuning)
05+06        ──> 03, 07  (hands and land are what livestock and scheduling need)
07 (animals) <── wheat engine from 04, for feed
04 (melon)   ──> 10, 14  (the premium race is a timing problem)
```

## If you only do three

**13**, **05+06**, **07**. The sweep harness makes every constant tunable against
a simulator we fully own; hire-and-expand is worth +76% today and is a day's
work; and the goose/fertilizer engine is where the remaining order of magnitude
lives.
