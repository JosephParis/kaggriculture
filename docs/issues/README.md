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

- **Submit through `submit.py`.** Submissions are rate-limited and cannot be
  withdrawn, so it runs a pre-flight -- stdlib-only imports, a full
  non-crashing game, p99 inside `actTimeout`, allowance not spent -- and
  refuses on any of them.
- **Never report a single game.** Weeds, shop unlocks and market noise make one
  result meaningless. Always a win rate over a batch, with the spread.
- Baseline to beat is whatever `main.py` currently scores against `starter`.
  Record it in the issue when it moves.
- Environment: **`py -3.12`**. The default `python` is a sandboxed Store 3.9 and
  `kaggle-environments` requires ≥3.11.

## Before starting anything

[../TRIED.md](../TRIED.md) lists every experiment already run and its
result. A good number of plausible ideas in this backlog have been tried
and lost — melon acreage, more hands, more land, strawberry, front-running
the opponent's melon dump. Check there first.

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

**Current baseline: 100% vs `starter`, median $101,402 over 12 paired games
(seeds 1000..1011).** Beat that number or it is a regression. Moved 20 August
by the wheat block (strawberry 44 -> 34), which is 21-3 head to head.
`py -3.12 eval.py --games 12 --seed 1000`. Note `eval.py` seeds randomly unless
`--seed` is given, so two runs without it are not comparable.

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
| [03](03-labour-scheduling.md) | Labour scheduling: assignment across many units | L | **open — sized: ~$12k/game ceiling, deprioritised** |
| 10 | Sell timing: dump `log` goods, meter `linear`/`sq` goods | M | **closed — the premise is wrong; dump everything** |
| 09 | Opponent modelling: both farms are visible | L | **partly done — worth ~1 game in 18** |

> **03, 23 August.** Cross-role help for idle units — a rancher whose herd is
> done doing crop work, and the reverse — was tried and **rejected** at every
> setting (6-14, 3-21, 2-22; capped to radius 1-4 it only reaches 8-8-8). The
> idle turns are slack held against the feeding peak. See
> [TRIED.md](../TRIED.md). What is left of 03 is the per-unit day tour.
>
> The same day's consolation prize came from taking the rejection seriously: if
> a rancher's worth is being in place for the feeding peak, the size of a feed
> trip decides whether it is — `FEED_CARRY` 6 → 4 was worth **19-5** on two
> seed sets. That sweep ran on the pre-wheat-block herd (8 cows / 4 sheep, 24
> melon), so the constant is in but **the baseline above predates it** and both
> want re-measuring on the current build.

### P2 — margins

| # | Issue | Effort | Status |
|---|---|---|---|
| 08 | Town shop demand: track unlocks, sell into scarcity | M | open |
| 11 | Submission pipeline and leaderboard tracking | S | open |
| 12 | Replay analysis tooling | M | **done — and it found the wheat block** |

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

**10**, **09**, **03** - the cheap production wins are spent and what is left
is the opponent. 03 was moved to the front on 20 August and is now moved back:
the tour it asks for has been *sized* (`tour_ceiling.py`) at a ceiling of ~$12k
a game, over-estimated, against a shared market that halves the score.

- ~~**10 (sell timing)**~~ **— closed 20 August; the premise was wrong.** It
  asked for premium goods to be metered. They must not be: the town drains
  milk 19/day, wool 13/day and strawberry 25/day, faster than two farms
  supply, so all three finish the season *above* base price (milk 1.9x,
  strawberry 2.5x) and there is no glut to protect against. Metering them
  **loses 8-16**, because the town drain is a race — held stock lets the
  opponent clear the same demand window first. Melon is the only good that
  crashes, and replanting its ground as strawberry banked +$5,254 and lost
  **2-22**. The incumbent's sell-everything-immediately rule is already right.
  See TRIED.md.
- **09 (opponent modelling)**, promoted back from P3 for the same reason. Both
  farms are public. Knowing whether the opponent is growing melon decides
  whether our second melon cycle is worth planting at all.
- **03 (labour scheduling)**, and it is now the *first* of the three rather
  than the last. The movement share was re-measured on 20 August
  (`action_stats.py`) and the premise turned over: movement is **42.8%**, not
  72%, and the new waste is **idle — 23.8% of all unit-actions are `PASS`**,
  almost entirely crop hands on days 1-9. Trying to fill that idle with wheat
  on bare ground banked +$6,214 and lost **0-24** — not because the router
  mis-scheduled it, but because holding melon tiles under a wheat cycle
  de-synchronised the melon block, and melon is a race into a market that never
  recovers. See TRIED.md; the idle is real and still unspent.

  The *cheap* way to spend it is now closed off too: handing idle units the
  other role's work was swept on 23 August and lost at every setting, best case
  a parity 8-8-8 reached only by shrinking the help radius until it did nothing.
  So the win has to come from planning a unit's day — a tour that keeps it near
  its herd *and* picks up crop work on the way — not from re-targeting it one
  turn at a time.

  The follow-up that issue then proposed — **priced routing**, scoring tasks by
  `value / (dist + 1)` — was built and **lost 4-20**, banking more against
  `starter` both times. It spends the idle on *walking* (movement 42.8% →
  47.5%, productive work down), because the only thing a one-step greedy router
  can do with a value signal is walk toward it. **The tour comes first; the
  price is only worth having once something can sequence.**

  The tour was then sized rather than built. Re-routing each unit-day optimally
  saves at most **616 movement actions/game, and 373 of those fall on days the
  unit was already idle** — leaving ~243 spendable, about **$12k/game and
  over-estimated**. The router is already within a quarter of optimal, so this
  is the item that shrank, not the one to do first.

Also worth knowing: **egg and wheat prices rise all season** (to ~$92 and ~$47
by day 28) because town shops drain them faster than we supply. Nothing in the
agent exploits that yet.
