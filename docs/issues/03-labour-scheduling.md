---
id: 03
title: "Labour scheduling: assignment across many units"
priority: P1
effort: L
status: open
---

## Where this stands

Half done. Two structural changes are banked:

- **Fixed per-unit territories** (`_territories`), serpentine-ordered, which
  stopped units oscillating across the board.
- **`URGENCY_W=0`** (18 August): a unit takes the *nearest* actionable task and
  urgency only breaks ties between equidistant ones. Worth 24-0 head to head
  and $83.0k -> $99.9k on bank.

The README asked for the movement share to be re-measured after that change,
since the often-quoted "72% of actions are movement" predates it. That
measurement is now in `action_stats.py`, and it says the premise has moved.

## The measurement, 20 August

`py -3.12 action_stats.py --games 3` (vs `starter`, seeds 1000-1002),
17,880 unit-actions:

| | share |
|---|---|
| movement (N/S/E/W) | **42.8%** |
| idle (`PASS`) | **23.8%** |
| productive | 33.4% |

Movement is down from 72% to 42.8%, so the routing work did what it claimed.
**Idle is the new headline**, and it is not spread evenly:

- By role: ranchers idle **1.1%** of their actions, crop hands **32.5%**.
- By day: days 1-9 run 40-85% idle. Days 1, 3 and 5 are **85% idle**.
- By hour: idle climbs from 7% in the morning to 66% by hour 23.

## Why the crop hands idle: the farm is bare, not finished

Per-day trace of one game (seed 1000), tiles outside the animal zone:

```
day  1 $ 300  crop-tiles 36  bare 15  planted 21  seeds {}
day  5 $ 220  crop-tiles 36  bare 15  planted 21  seeds {}
day 10 $ 120  crop-tiles 36  bare 15  planted 21  seeds {}
day 11 $8626  crop-tiles 60  bare 52  planted  7  seeds {STRAWBERRY: 34, MELON: 19}
day 22 $30888 crop-tiles 60  bare 12  planted 43  seeds {}
day 25 $59658 crop-tiles 60  bare 29  planted 31  seeds {}
day 28 $85249 crop-tiles 60  bare 30  planted 30  seeds {}
```

Two separate windows of bare ground, for two different reasons:

1. **Days 1-10: cash-starved.** Everything is spent on day 0-1 on animals and
   melon seed. The bank sits at $300 falling to $120 (the daily hire bill is
   ~$20), `LAND_CASH_BUFFER` blocks any further seed purchase, and there is no
   income at all until the first melon harvest lands on day 11. Fifteen tiles
   sit bare for ten days while six hired hands idle 85% of their actions.
2. **Days 20-28: past the planting cutoff.** Melon and strawberry both have a
   last-plant day of 19, so once it passes nothing is ever planted again.
   Twenty-nine tiles sit bare for the last eight days, with $40k-$85k in the
   bank and a full crew idle.

Neither window is a scheduling problem. Better assignment cannot fill a tile
that has nothing to plant on it.

## What was tried, and why it failed

Filling both windows with wheat (`BRIDGE_EARLY`, `BRIDGE_LATE`, `BRIDGE_MELON`
in `main.py`, all defaulting to 0). Four variants, **all 0-24 head to head**,
all of them banking *more* against `starter`. Full write-up in TRIED.md.

The correction that matters for this issue: **the bare ground is not idle, it
is reserved.** The farm plants out every empty tile the moment the day-11 melon
money lands, and wheat still growing on those tiles delays it -- both premium
blocks reach full acreage about four days late, which is two of strawberry's
four yields. Empty ground before day 11 is buying an option, and the option is
worth more than a wheat cycle.

So the idle is real, it is large, and **it cannot be spent on the land**.
Anything that uses it has to not occupy a tile.

## Priced routing: built, and rejected

The section above proposed scoring tasks by `value / (dist + 1)` on the
grounds that `URGENCY_W=0` is value-blind. That was built on 20 August
(`PRICED_ROUTING`, `PRICED_URGENT_TIER` in `main.py`, both defaulting to 0;
`variants/priced-routing.py` and `variants/priced-routing-v2.py`).

**It lost 4-20 over 12 paired games a seat, in both forms**, while banking
*more* against `starter` -- the bridge-wheat signature again. Full write-up in
TRIED.md. The tally is the useful part:

| | incumbent | priced |
|---|---|---|
| movement | 42.8% | **47.5%** |
| idle (`PASS`) | 23.8% | **20.0%** |
| productive | 33.4% | **32.5%** |

It spends the idle, exactly as intended, and spends it on **walking**: 675
fewer `PASS` against 841 more movement actions, with productive work down 166.
Melon is worth ~10x a wheat task, so dividing by distance still sends a unit
across its block to reach it, and the work it passes goes undone.

**The diagnosis in the section above was wrong.** The router is not mispricing
tasks. A greedy one-step router cannot *spend* a value signal at all: the only
move available to it is "walk toward the expensive thing", and the walk is the
cost. Being value-blind is what made `URGENCY_W=0` worth 24-0.

## The tour, sized

`tour_ceiling.py`, 3 games, seeds 1000-1002. The workload is held fixed: for
each unit-day it takes the tiles the unit actually stopped at and computes the
shortest path from where it started, then compares that against the movement
actually spent.

| | per game |
|---|---|
| movement actually spent | 2,539 |
| perfect-routing lower bound | 1,923 |
| **ceiling on what any tour saves** | **616 (24.3% of movement)** |

Two things fall out, and the second is the one that matters:

1. **The greedy router is already within a quarter of optimal.** Fixed
   territories, serpentine blocks and `URGENCY_W=0` took most of what the
   geometry had to give. There is no factor-of-two hiding in the routing.
2. **Most of the remaining saving cannot be spent.** Splitting by whether the
   unit had any idle time that day:

   | | per game | unit-days |
   |---|---|---|
   | savings on unit-days *with* idle | 373 | 456 |
   | savings on unit-days with none | **243** | 260 |

   A unit that walks less on a day it was already idle for just idles earlier.
   Only the 243 are worth anything, which at ~$51 a productive action is
   **~$12k/game against a ~$100k bank**.

And 243 is an over-estimate on three counts, all of them in the tool's
docstring: it reorders the day with hindsight a morning plan cannot have, it
ignores the growth windows that force a tile to be visited twice, and it
assumes every freed step turns into productive work.

## Next

1. **Do not build the tour first.** It is an L-effort change with a measured
   ceiling of ~12% of bank against `starter`, and the mirror is worth less
   still. Self-play halves the score, so issue 10 (sell timing) and issue 09
   (opponent modelling) are contesting a far larger pool. If the tour does get
   built, build it for the h2h margin -- small systematic deficits flip every
   game in this repo -- and not for the bank.
2. **Do not spend more effort filling the idle** until there is a use for it
   that needs no tile. Bridge wheat showed it cannot be spent on land, priced
   routing showed it cannot be spent on walking, and the sizing above shows
   that most of the walking is not even worth removing. The remaining
   candidates are elsewhere in the backlog (issue 10, sell timing; issue 08,
   the town shops).

Worth recording for whoever picks this up: `h2h.py` in this repo sweeps.
The null control (two identical agents) ties 8-8-8, and every real change
measured here came back 0-24 or 24-0. A 24-0 means "consistently better", not
"much better", and small systematic deficits flip every game.
