# Strategy

Written 17 August 2026, after reading the environment source and running the
labour experiment below. Supersedes the ordering in
[issues/README.md](issues/README.md).

## The finding that reframes the repo

**The full environment source is on this machine.**

```
C:\Users\joeyk\AppData\Local\Programs\Python\Python312\Lib\site-packages\
  kaggle_environments\envs\kaggriculture\kaggriculture.py     (1086 lines)
  kaggriculture.json                                          (the spec)
```

Every constant, the exact price function, the turn order, the daily refresh, and
the three built-in opponents are all readable. Nothing about this game needs to
be measured by probing. Issue 02 proposed recovering the price curve
empirically; that is now a five-line script against `market_price()`, and the
results are tabulated below.

This changes the shape of the work. We are not exploring a black box, we are
optimising against a known simulator. The remaining uncertainty is entirely
about *policy* — what to do with 720 turns — not about *mechanics*.

## Three constraints that bound every design

1. **`actTimeout: 1`** (from `kaggriculture.json`). One second per turn, 720
   turns. No per-turn search, no MCTS, no rollouts. The agent has to be fast
   greedy assignment against a precomputed plan. This is the hardest design
   constraint and it should be respected from the first line of code.
2. **Market orders are free.** They cost no unit-actions — only the
   10-per-turn cap. Selling is never a tradeoff against farming. The real cost
   of selling is getting produce into the shed: harvest, walk, `DROP`.
3. **Shed capacity is 100 items and overflow at end-of-day is discarded.** A
   farm producing 80 units/day must sell every turn or lose the excess.
   `BUY_PRODUCT` also fails when the shed is full, so `SELL` orders go ahead of
   `BUY` orders in the queue.

## The economic map

### Actions are the currency

Nothing here is scarce except unit-actions. Money stops being scarce around day
6, land around day 10, seeds never. Every decision should be priced in
**dollars per action**.

| Engine | Actions per cycle | Revenue | $/action | Ceiling |
|---|---|---|---|---|
| **Melon** | 13 over 11 days (plant, 11x water, harvest) | 6 melons @ ~$217 = $1,302 | **~$100** | market saturates at ~120 units |
| **Fertilizer** (from animals) | 1 (`COLLECT_FERTILIZER`) | $100 falling to $60, then $20 | **~$80 falling** | ~$25k total, **shared, never recovers** |
| **Goose / eggs** | ~5/day/tile (feed, care, collect, half a harvest, walking) | 2 eggs + 1 fertilizer ~= $140/day | ~$28 | effectively unlimited |
| **Wheat** | 7 over 5 days | 4 wheat @ ~$21 = $84, less $10 seed | ~$11 | effectively unlimited |
| Cow / sheep | similar to goose | milk and wool crash by unit 50 | high, then zero | ~50 units each |

### What the market will actually absorb

Cumulative revenue from selling N units into a fresh market, computed against
`market_price()`. Town demand drains inventory over the season and pushes these
numbers *up*, so they are conservative.

| | 25 | 50 | 100 | 200 | 400 | 800 |
|---|---|---|---|---|---|---|
| **EGG** | $1,151 | $2,244 | $4,371 | $8,510 | $16,559 | **$32,199** |
| **WHEAT** | $577 | $1,127 | $2,193 | $4,293 | $8,313 | **$16,243** |
| **FERTILIZER** | $2,440 | $4,755 | $9,010 | $16,020 | $24,040 | $25,352 |
| **MELON** | $6,202 | $12,098 | **$21,721** | $26,527 | $26,727 | $27,127 |
| **CARROT** | $782 | $1,482 | $2,738 | $4,832 | $7,853 | $10,596 |
| **TOMATO** | $1,295 | $2,411 | $4,318 | $7,221 | $10,453 | $11,399 |
| **WOOL** | $4,715 | $7,655 | $7,969 | $8,069 | $8,269 | $8,669 |
| **MILK** | $3,372 | $5,430 | $6,205 | $6,305 | $6,505 | $6,905 |
| **STRAWBERRY** | $2,424 | $3,648 | $3,847 | $3,947 | $4,147 | $4,547 |

Three regimes, set by the `above_func` in `MARKET_PARAMS`:

- **`log` — unlimited sinks.** Wheat and egg barely move. Wheat holds ~$20 at
  any volume, egg holds ~$40. These are the bulk engines.
- **`sqrt` — moderate.** Carrot and tomato absorb a few hundred, then sag.
- **`linear` / `sq` — premium, tiny volume.** Strawberry, milk and wool are at
  the $1 floor by unit 50–60. Melon is the exception worth playing: the first
  ~100 units are worth $21,721.

### The two races

Because the market is shared, premium goods are first-come-first-served:

- **Fertilizer never recovers.** No shop and not the town center consumes it
  (`TOWN_CENTER_PRODUCTS` excludes it), so its inventory only ever rises. It is
  a one-way ~$25k pool split between the two players. Get animals down early and
  dump fertilizer early — every unit the opponent sells first is $0.20 off every
  unit we sell after.
- **Melon crashes permanently at ~150 units** and drains only 1/day from the
  town center. Whoever harvests first takes $217/unit and the other player gets
  the floor. Selling our own melons *is* the denial play; no separate griefing
  is required.

Eggs and wheat are the opposite case. Shops drain them continuously — 5 of the 8
shop types demand wheat, 2 demand eggs — so their prices recover and even rise
late in the season.

### Never fertilize

`FERTILIZE` doubles the watering bonus for 3 days. Priced out:

- Wheat goes 4 → 6 units (+2, about $42). Carrot 3 → 4 (+1, about $30). Tomato
  gains ~2 over the fertilised window (about $25). Melon reaches its cap two
  days early, saving two tile-days.
- A fertilizer unit sells for $60–$100.

Every use is a loss. **Fertilizer is a cash crop, not an input.** This also means
animals stay worth their tile after their product has crashed: fertilizer
accrues whether or not the animal was fed that day, so a neglected cow still
prints one collectable unit every morning.

## The labour experiment

The backlog already suspected labour was the binding constraint. The hire curve
makes it stark — cost is `fib(n)` for the n-th hire *of that day*, and it resets
every morning:

| hands | marginal | per day | per season | extra actions/day |
|---|---|---|---|---|
| 4 | $3 | $7 | $210 | 96 |
| 8 | $21 | $54 | $1,620 | 192 |
| 10 | $55 | $143 | $4,290 | 240 |
| 12 | $144 | $376 | $11,280 | 288 |
| 14 | $377 | $986 | $29,580 | 336 |

At 8 hands a unit-action costs **$0.28**. A wheat action returns $11. Labour is
effectively free until roughly the 12th hand, where the marginal hand costs
$6/action.

Tested by bolting `HIRE` onto the current baseline and widening `PLOT` to the
whole NW quadrant — 4 games each against `starter`, median final balance:

| hands | median | vs baseline |
|---|---|---|
| 0 | $6,186 | — |
| 2 | **$10,015** | +62% |
| 4 | **$10,878** | +76% |
| 8 | $9,316 | +51% |

Two hands nearly doubles the score, for $2/day. The fall-off at 8 is not a
labour problem: the NW quadrant has 24 workable tiles, and at
`TILES_PER_UNIT = 6` four units already saturate it.

**Hiring and land buy each other.** Hands are worthless without tiles, tiles are
worthless without hands. Land is $1k / $2k / $4k for 25 tiles each, which at
wheat rates alone pays back in about two days of the labour it unlocks.

## The plan

A season in four overlapping phases. Each is a bet that the previous one has
paid for it.

**Days 0–3, cash engine.** Wheat on the NW quadrant, 2–4 hands from day 0 at
$7/day. Wheat is the fastest cycle *and* the only animal feed, so it is a
prerequisite either way. Sell everything.

**Days 2–6, buy the board.** `BUY_LAND` as soon as each $1k / $2k / $4k clears,
scaling hands with tiles at roughly one hand per 6 tiles. The full board is 100
tiles and ~16 units, which is past the economic hiring limit, so the real target
is ~10–12 hands working ~70 tiles.

**Days 3–10, livestock and the fertilizer race.** Every goose is $300 plus one
`BUILD_COOP` and pays back in about 3 days. Geese beat cows and sheep outright:
eggs are a `log` sink that never crashes, milk and wool are dead by unit 50. Buy
wheat as feed if own production falls short. Fertilizer collection starts the
day after placement and is the highest-value single action in the game.

**Days 0–20, melon on a slice of the board.** Roughly 15–18 tiles of melon in
staggered batches, so harvests land early rather than all at once on day 25.
Worth about $20k if we get there first. Anything planted after day 19 never
matures.

**Endgame, days 27–30.** Unsold inventory scores zero. Stop planting anything
that will not yield, empty the shed, and dump the premium goods that were being
drip-fed.

A rough ceiling on that plan is $30k–50k from eggs and fertilizer plus ~$20k
from melon. The current baseline is $6k. There is an order of magnitude on the
table, which means the first job is not fine-tuning — it is building the engine
at all.

## What this implies for the backlog

- **02 (measure the market) — close it.** Answered by reading the source, and
  the numbers are in this document. Do not spend a day probing.
- **New P0: an offline sweep harness.** We own the exact rules and a game runs
  in 2.2s. A harness that sweeps policy parameters — hands per tile, crop mix,
  goose count, melon acreage, sell thresholds — over batches is worth more than
  any hand-tuned heuristic. This is the compounding investment.
- **05 (hiring) and 06 (land) merge and move to P0.** They are one decision and
  they are worth +76% today.
- **07 (livestock) moves to P0.** Geese are the main engine, not a P2 refinement.
- **09 (opponent modelling) drops to P3.** With an order of magnitude between us
  and our own baseline, reacting to the opponent is premature. The only
  opponent-aware behaviour that matters early is the fertilizer and melon race,
  and that reduces to "sell premium goods early" — no model required.
- **10 (sell timing) stays P2 and shrinks.** The rule is nearly static: dump
  `log` goods continuously, meter `linear` and `sq` goods, clear everything by
  day 29.

## Working rules that still hold

- **Never submit from an unattended run.** Rate-limited, cannot be withdrawn.
- **Never report a single game.** Batch median and spread, always.
- `py -3.12`. The default `python` is a sandboxed Store 3.9.
- Respect `actTimeout: 1`. Measure per-turn wall clock in the harness, because
  an agent that times out on Kaggle scores nothing regardless of its policy.
