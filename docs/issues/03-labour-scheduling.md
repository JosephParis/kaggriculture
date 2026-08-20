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

## Next

Two things, in order:

1. **Do not spend more effort filling the idle** until there is a use for it
   that needs no tile. The obvious candidates are all elsewhere in the backlog
   (issue 10, sell timing; issue 08, the town shops).
2. **The lookahead half of this issue is still open and still untouched.**
   Units take one greedy step per turn with no per-day tour and no coordination
   between them. Movement is 42.8% of actions, so the ceiling on tour planning
   is real but bounded -- and note that it is now a *smaller* prize than the
   23.8% idle that has just been shown to be unspendable. Size it before
   building it.

Worth recording for whoever picks this up: `h2h.py` in this repo sweeps.
The null control (two identical agents) ties 8-8-8, and every real change
measured here came back 0-24 or 24-0. A 24-0 means "consistently better", not
"much better", and small systematic deficits flip every game.
