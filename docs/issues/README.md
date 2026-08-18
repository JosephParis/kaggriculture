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
| [13](13-sweep-harness.md) | Parameter sweep harness over batched games | M | **done** |
| 05+06 | Hire-and-expand: hands and land scale together | M | **done** |
| [07](07-livestock.md) | Livestock: the goose/egg/fertilizer engine | L | **done** |
| [04](04-melon.md) | Crop mix: melon for the premium slice | M | **done** |

**Current baseline: 100% vs `starter`, median $51,018 over 12 games (theirs
$3,519).** Beat that number or it is a regression. `py -3.12 eval.py --games 12`.

Where it came from:

| | median vs `starter` |
|---|---|
| Original single-farmer wheat loop | $6,024 |
| Hire, expand, hold territory | $14,724 |
| Goose/egg/fertilizer engine | $28,442 |
| Melon, and harvesting before the egg cap | $48,857 |
| Endgame liquidation | **$51,018** |

Swept defaults, all on paired seeds: 12 coops, 20 melon tiles, 2 quadrants,
8 tiles per unit, feed grown rather than bought.

**$51,018 is an upper bound, not an expectation.** Two copies of this agent land
at ~$25k each, because they crash each other's melon, fertilizer and egg prices.
The leaderboard is not `starter`. Measure against `--opponent main.py` too.

Labour was the binding constraint early: the first baseline planted 15 tiles,
could not water them, and the farm was weeds by day 6 — final profit $46.
Sizing the plot to the workforce took it to $3,024. The correction to that
lesson is that the answer was never "plant less", it was "hire more, buy land,
and put geese and melon on the good tiles".

### P1 — making the engine sharp

| # | Issue | Effort | Status |
|---|---|---|---|
| 15 | Rancher action budget: eggs sit at the `max_held` cap | M | **done** |
| 14 | Endgame: liquidate by day 29, unsold inventory scores zero | S | **done** |
| [03](03-labour-scheduling.md) | Labour scheduling: assignment across many units | L | open |
| 10 | Sell timing: dump `log` goods, meter `linear`/`sq` goods | M | open |
| 09 | Opponent modelling: both farms are visible | L | open |

### P2 — margins

| # | Issue | Effort | Status |
|---|---|---|---|
| 08 | Town shop demand: track unlocks, sell into scarcity | M | open |
| 11 | Submission pipeline and leaderboard tracking | S | open |
| 12 | Replay analysis tooling | M | open |

### P3 — nothing here at the moment

Issue 09 (opponent modelling) was demoted here while our own baseline was an
order of magnitude away. It is back in P1: the production wins are spent, and
self-play says the opponent is now where the score is.

## Dependencies

```
01 (harness) ──> everything: nothing can be measured without it
13 (sweeps)  ──> 04, 05+06, 07, 10  (every policy constant wants tuning)
05+06        ──> 03, 07  (hands and land are what livestock and scheduling need)
07 (animals) <── wheat engine from 04, for feed
04 (melon)   ──> 10, 14  (the premium race is a timing problem)
```

## If you only do three

**10**, **09**, **03** - the cheap production wins are spent, and what is left
is the opponent.

- **10 (sell timing)** because self-play still halves the score. Against
  `starter` we make $51k; against a copy of ourselves, $25k. Every remaining
  point is in the shared market.
- **09 (opponent modelling)**, promoted back from P3 for the same reason. Both
  farms are public. Knowing whether the opponent is growing melon decides
  whether our second melon cycle is worth planting at all.
- **03 (labour scheduling)** because ~65% of unit-actions are still movement.
  Territories and a distance tiebreak got it from 72%; the rest needs actual
  routing rather than one greedy step at a time.

Also worth knowing: **egg and wheat prices rise all season** (to ~$92 and ~$47
by day 28) because town shops drain them faster than we supply. Nothing in the
agent exploits that yet.
