# What has been tried

A log of every experiment run against this agent, kept so nobody re-runs a
losing one. Last updated 20 August 2026.

Read [STRATEGY.md](STRATEGY.md) first for the economics, then this for the
record of what those economics actually bought.

**Current agent: `main.py`** — 8 cows / 4 sheep, 24 melon, strawberry on all
remaining land, **no wheat** (feed is bought), three quadrants, and units
routed to the **nearest** actionable task rather than the most urgent one.
Median $99.9k against `starter`, 12/12. Beats the previous build 24-0 head to
head, both seats.

Bank against `starter` is a filter, not the objective — the ladder scores
win/loss/tie. The build before this one went the other way: its bank fell from
$88.5k to $84.5k while its head-to-head went decisively up.

---

## How to test anything here

Five tools, the first three in increasing order of trustworthiness:

```
py -3.12 eval.py   --games 12                      # bank vs starter: a filter
py -3.12 sweep.py  KNOB=a,b,c --games 12           # paired-seed parameter grid
py -3.12 h2h.py    cand.py --base main.py --games 12   # win rate, both seats
py -3.12 action_stats.py --games 3                     # what the crew does all day
py -3.12 tour_ceiling.py --games 3                     # what better routing could ever save
```

`action_stats.py` is a tally, not a test: unit-actions by operation. Nothing in
this agent has ever shown up in the score before it showed up in the tally.

`h2h.py` was given a null control on 20 August -- two behaviourally identical
agents -- and returned **8W 8L 8D, 4-4 in each seat**. So a lopsided h2h result
is the agent, not the harness.

**`h2h.py` is the objective.** The ladder rates on win/loss/tie only; coin
margin buys no rating. Bank against `starter` has been actively misleading
more than once — two herd configurations within $600 of each other on bank
went 11-5 head to head, and turning `CARE` off looked free on bank but loses
0-20 head to head.

The sharpest case is bridge wheat (20 August): **+$6,214 on bank, 0-24 head
to head.** The two measures did not disagree on magnitude, they disagreed on
sign, decisively, in both directions at once. `starter` does not compete for
melon, so against it a change that trades melon yield for wheat volume reads as
pure addition; in a mirror, the melon given up is melon the opponent takes.

Five rules learned the hard way, each after getting a result backwards:

- **Never compare on unpaired games.** An early 4-game unpaired comparison said
  the distance tiebreak was a $3,400 regression; 10 paired games said it was a
  $3,600 improvement. The sign was wrong, not just the magnitude.
- **Use at least 12 games a seat.** A 6-game panel rated a melon-20 build level
  with the incumbent; 28 games had it losing 2-26.
- **Sample a range wide enough to contain the optimum.** Strawberry was
  rejected twice on tests at 8 and 14 tiles, both of which genuinely lose.
  The curve is not monotonic: 16 wins and it improves all the way to filling
  the farm. Two points on the wrong side of a threshold look exactly like a
  dead idea.
- **Re-derive every allocation after a structural change, not just the knob
  you changed.** Turning on bought feed made wheat redundant; melon and
  strawberry acreage had both been fitted against a farm that grew wheat, and
  both were badly wrong afterwards (melon 16 -> 24, strawberry 0 -> 44).
  This has now caused three separate wrong conclusions.
- **Test against recorded opponents, not only a mirror** (`opponents/`).
  The mirror is not useless -- it did rate strawberry correctly once the range
  was right -- but the real-opponent test is what exposed the farm sitting
  two-thirds empty in the first place.

---

## Mechanics worth knowing before proposing anything

- **The environment source is installed locally**, at
  `kaggle_environments/envs/kaggriculture/kaggriculture.py`. Read it. Nothing
  about this game needs to be discovered by probing.
- **`actTimeout` is 1 second** across 720 turns. No search, no rollouts. The
  agent is greedy assignment and must stay that way. Current p99 is 0.8ms.
- **Market orders cost no unit-actions**, only the 10-per-turn cap. Selling is
  never a tradeoff against farming.
- **`SELL` only sees the shed.** `HARVEST` puts produce in a unit's inventory;
  `_end_of_day` moves it to the shed for free. Walking to the shed to store
  things is wasted motion — the old baseline burned much of its day on it.
- **Shed cap is 100 and overflow is destroyed.** ~49 units a season are lost
  this way. Delivering more often to prevent it costs more than it saves.
- **Unsold inventory scores zero**, and the end-of-day drop runs *after* the
  reward is taken, so the last day needs an explicit liquidation.
- **Town drain is what holds premium prices up**, and the original strategy doc
  missed it entirely: strawberry 25/day, milk 19/day, carrot 19/day, wool
  13/day, egg 13/day, tomato 13/day, wheat 31/day. **Melon 1/day and
  fertilizer 0/day** — those two never recover, everything else does.
- **Animal value per tile per day**, with `CARE` banking +1 daily:
  sheep $267 (payback 1.9d), cow $240 (1.7d), goose $100 (3.0d).
- **Never `FERTILIZE`.** The yield bonus is worth $25-42; the fertilizer sells
  for $60-100. It is a cash crop, not an input.

---

## Accepted — these are in `main.py`

| # | Change | Effect |
|---|---|---|
| 1 | Hire hands every morning, sized to the work | $6.0k → ~$10k on its own |
| 2 | Buy NE+SW — **two purchases, three quadrants** | matches the public meta |
| 3 | Fixed per-unit territory for the day | stopped units oscillating |
| 4 | Serpentine block ordering | distance-ordered blocks are diagonal arcs |
| 5 | Distance tiebreak within an urgency tier | movement 72% → 65% of actions |
| 6 | Water only for survival or yield window | 4 actions instead of 5 per wheat |
| 7 | Stop walking to the shed to store produce | end-of-day drop is free |
| 8 | Cows + sheep instead of geese | $51k → $60k |
| 9 | Buy wheat feed from the market | +$9k, *only* once animals were cows/sheep |
| 10 | Melon on 16 tiles | +$20k, the single biggest change |
| 11 | Harvest-at-cap outranks fertilizer collection | 112 eggs/season → 4 |
| 12 | Endgame liquidation from hour 15 on day 29 | +$1.3k |
| 13 | Cap animal purchases by *placeable* tiles | animals cannot be sold |
| 14 | Seed spend against a running balance | latent; three crops emptied day 0 |
| 15 | 8 cows / 4 sheep | beat 6/6 by 15-1 head to head |
| 16 | Strawberry on every tile the herd and melon do not use | $74.7k → $88.5k |
| 17 | Melon 16 → 24 tiles | 25-7 h2h, bracketed by 16 and 30 |
| 18 | `URGENCY_W=0`: nearest task first, urgency only breaks ties | **24-0 h2h**, $83.0k → $99.9k |

**Note on 9:** feed buying was correctly rejected for the goose farm and
correctly accepted for the cow/sheep farm. The same knob flipped sign when the
animals changed. Re-test knobs after structural changes.

---

## Rejected — do not re-run these without a new reason

### Structural

| Idea | Result |
|---|---|
| A **fourth** quadrant (`MAX_LAND=3`) | $12.5k vs $9.4k; loses again later |
| Four quadrants + 10-12 hands + bigger herd | 0-24 — **but see the correction below** |
| Hiring floor of 8 / 10 / 12 hands | 3-21, 3-21, 0-24 (mirror only) |
| `TILES_PER_UNIT` 6 / 10 | 1-15, 0-20 |
| Rancher density `GEESE_PER_RANCHER` 4 / 6 | worse, 0-28 at 6 |

> **Correction, 18 August.** `MAX_LAND` counts *purchases*, and NW is free, so
> our default `MAX_LAND=2` already gives **three quadrants** — the same land
> the public meta takes. The "meta shape" experiment above actually tested a
> **fourth** quadrant, which the notebooks say leaders rarely buy. It was
> never a test of the meta, and the conclusion drawn from it — that the
> leaders' advantage is routing rather than configuration — is not supported
> by it.

> A second arithmetic error ran through all of the above: much of this work
> assumed 46 workable tiles, i.e. two quadrants. The real figure with three
> quadrants is ~71. **We own 75 tiles and a traced game uses 14 of them.**
> The plot cap (`TILES_PER_UNIT` x units) leaves most of the farm idle, which
> is a far more likely explanation of the gap than routing.

### Crops

| Idea | Result |
|---|---|
| Melon 8 / 12 / 16 / 30 / 36 / 44 tiles | all lose to **24**; the old "16 is optimal" was fitted against a wheat farm |
| Melon planting cutoff day 9 | $8k worse |
| Melon planting cutoff day 13 | tied (submitted as v5) |
| ~~Strawberry~~ | **Wrong — now accepted at 44 tiles.** 8 and 14 do lose; the curve is not monotonic and 16+ wins big |
| Geese at any count | superseded by cows/sheep |

The strawberry row above was wrong for a long time and is kept as a warning.
Four units off one planting is only 0.24/tile/day, which is what the original
reasoning fixated on — but it is still nearly double a wheat tile, and once
feed is bought there is nothing better to do with the land.

### Land use

| Idea | Result |
|---|---|
| **Bridge wheat onto bare ground** (`BRIDGE_EARLY`, `BRIDGE_LATE`) | **0-24**, in every variant tried -- while banking +$1,200 to +$6,214 vs `starter` |

Four variants, all 0-24 head to head in both seats: both windows, early only,
and both again with melon-zoned ground protected (`BRIDGE_MELON=0`). The bank
against `starter` went *up* every time.

The diagnosis behind it stands and is worth keeping: the farm really does sit
with 15 tiles bare through days 1-10 (cash-starved, bank at $300 falling to
$120) and 29 bare through days 20-28 (past both planting cutoffs), while crop
hands idle 32.5% of their actions. Planting wheat on that ground raises the
bank a lot and raises the floor even more -- worst of 12 seeds went $78.6k to
$97.1k.

Two mechanisms were proposed and only the second survived tracing.

*Not* value-blind routing. The first guess was that `URGENCY_W=0` lets cheap
wheat work steal melon waterings. Planting counts barely move (melon 146 ->
143, strawberry 115 -> 113 over three games), so that is not what happens.

**The bare ground is not idle, it is reserved.** Day-by-day traces of one game,
counting planted tiles outside the animal zone:

| | melon hits 24 | strawberry hits 36 |
|---|---|---|
| incumbent | day 13 | **day 13** |
| bridge (melon protected) | day 16 | **day 17** |

The farm is cash-starved until the first melon harvest lands on day 11, and the
moment it does it plants out every bare tile at once. Wheat on those tiles is
still growing when the money arrives, so **both premium blocks reach full
acreage about four days late**. Four days is two of strawberry's four yields
(ages 10, 12, 14, 16), and it costs melon its synchronised second cycle -- with
melon-zoned ground unprotected the count wanders all season, 13/15/18/22/19/21
instead of sitting flat at 24, and day 11 banks $4.7k instead of $8.6k.

Melon is a **race into a market that never recovers**: the town drains 1/day,
the curve is quadratic in the glut, and the first seller takes ~$217 a unit. So
trickled melon sells into a market our own earlier melon crashed.

Why the bank disagrees so violently: `starter` contests neither melon nor
strawberry, so against it the extra tilled ground is pure added volume and the
premium delay costs little. In a mirror the two banks are otherwise nearly
identical -- the null control ties 8-8-8 -- so a systematic premium deficit of
any size flips every game. **A 24-0 in this repo does not mean "much better",
it means "consistently better", and small perturbations sweep.**

**The general lesson: premium acreage wants to go in as one block the instant
cash allows, and empty ground before day 11 is buying that option.** Filling it
costs more than it earns. The idle measured in issue 03 is real and still
unspent, but it cannot be spent on the land -- if anything is to use it, it has
to be something that does not occupy a tile.

All three knobs are in `main.py` defaulting to 0.

### Routing

| Idea | Result |
|---|---|
| **Priced routing**: rank tasks by `value / (dist + 1)` (`PRICED_ROUTING`) | **4-20**, in both forms tried -- while banking +$796 and +$1,472 vs `starter` |

This is the change issue 03 proposed after the bridge-wheat post-mortem, on the
reasoning that `URGENCY_W=0` left task choice **value-blind**: it minimises
distance and uses the tier only to break exact ties, so a cheap task standing
near an expensive one steals the action. Pricing each task at the dollars it
earns over the actions it costs -- the walk included, since reaching a tile `d`
steps away and acting costs `d + 1` -- was supposed to fix that.

It lost, twice, and the tally says why. Two variants, 12 paired games a seat:

| | bank vs `starter` | h2h vs `main.py` |
|---|---|---|
| incumbent | $100,890 | -- |
| v1, everything priced | $101,686 | **4-20-0** |
| v2, rescue tiers kept absolute + `DIG` unpriced past the cutoff | $102,362 | **4-20-0** |

v2 exists because v1 had a real bug: it let *survival* compete on price, and a
dying wheat plant is worth 4 x $21 against a melon watering at $217, so the
plant loses the auction and is a weed by morning. Protecting `T_RESCUE`
(`PRICED_URGENT_TIER`) and refusing to pay for digging ground past its planting
cutoff both fixed genuine defects -- and moved the result not at all. The
mechanism was never the rescues.

**Priced routing converts idle into walking, not into work.**
`action_stats.py`, 3 games, seeds 1000-1002:

| | incumbent | priced |
|---|---|---|
| movement | 42.8% | **47.5%** |
| idle (`PASS`) | 23.8% | **20.0%** |
| productive | 33.4% | **32.5%** |

It does what it was asked -- idle falls by 675 actions -- but 841 actions go
*into movement* and productive work falls by 166. `HARVEST` drops 747 -> 690
and `COLLECT_FERTILIZER` 593 -> 570.

The reason is that dividing by distance does not price the walk anywhere near
steeply enough. Melon is worth ~10x a wheat task, so `value / (dist + 1)` will
send a unit ten tiles across its block to reach it, and everything it walked
past goes untouched that turn. `URGENCY_W=0` won 24-0 precisely *by* being
value-blind, and pricing partially undoes it.

**So "value-blind" was the wrong diagnosis of the bridge-wheat failure.** The
router is not mispricing tasks; a greedy one-step router simply cannot spend a
value signal, because the only thing it can do with "that tile is worth more"
is walk toward it, and the walk is the cost. A value signal needs a structure
that can *sequence* -- the per-day tour -- before it is worth anything. Priced
routing without a tour is strictly worse than no pricing at all.

The knobs are in `main.py` defaulting to 0, and the variants are kept, so this
is re-runnable rather than re-derivable.

### Herd

| Composition | Result |
|---|---|
| **8 cows / 4 sheep** | **current best** |
| 6/6 | −15 vs current |
| 8/5 | −4 (submitted as v4) |
| 10/8, 4/8, 8/2, 12/4, 10/4, 10/6, 8/6, 8/8 | all clearly worse |

Sheep are worth more per tile per day than cows in isolation, yet sheep-heavy
builds lose. Unexplained; possibly wool's lower town drain (13 vs 19/day), or
the 3-day interval interacting with `max_held`.

### Logistics and market

| Idea | Result |
|---|---|
| Daily flush (deliver from hour 18/21) | much worse; walking beats the ~49 units saved |
| `DROP_THRESHOLD` 5 / 8 | 14 stays best |
| `FEED_CARRY` 14 | far worse — it exceeds `DROP_THRESHOLD`, so a unit picks up feed and immediately turns round to deliver it |
| **Front-run the opponent's melon dump** | **0-24**, and 2-22 even when gated to units carrying melon |
| `CARE_ENABLED=0` | 0-20 — CARE is essential despite looking free on bank |
| `GOOSE_CASH_BUFFER` 300 | 6-14 |
| `GOOSE_BUY_RATE` 6, `GOOSE_START_DAY` 1 | no-ops; the knobs never bind |

The front-run is Hamburger's published idea and it is sound in principle —
both farms are public, melon never recovers, first seller takes $217/unit. It
fails here purely on action economy: breaking off to deliver costs more than
winning the melon price is worth.

---

## Where we actually stand

Five submissions on 18 August, all rating near the 600 starting value against
leaders at ~3190:

| | local vs `starter` | ladder |
|---|---|---|
| v1 geese + melon | $51k | 628 |
| v2 cows+sheep, bought feed | $77k | 590 |
| v3 8c/4s (= `main.py`) | $75k | 596 |
| v4 8c/5s | $72k | pending |
| v5 melon cutoff day 13 | $72k | pending |

Ratings warm from 600 and five instances split the episode pool, so these are
noisy. But the public notebooks warn that a farm printing 100-170k against
`starter` can still sit mid-ladder, and we print 75k.

---

## Open leads, best first

1. **Replay analysis of a loss to a strong opponent.**
   `py -3.12 -m kaggle competitions replay <episode_id>`, then diff their
   turn-by-turn routing against ours. Everything above says the remaining gap
   is execution, and this is the only way to see it directly. Nothing else on
   this list is worth doing first.
2. **Routing — partly banked, 18 August.** Task choice used to be strictly
   lexicographic on urgency, so a unit walked across its block to the most
   urgent tile and past everything else. Scoring `tier * URGENCY_W + dist` and
   setting `URGENCY_W=0` — nearest actionable task, urgency only as a tiebreak
   — was worth 24-0 head to head and $83.0k → $99.9k on bank.
   What is left is the larger half: the agent still picks one greedy step per
   unit per turn, with no lookahead and no coordination between units. A real
   tour per unit per day is the next structure, and it is what would make three
   quadrants and 12 hands pay.

   **Re-measured 20 August, and the premise moved.** Movement is **42.8%**, not
   72%. What replaced it is **idle: 23.8% of all unit-actions are `PASS`** --
   entirely crop hands (32.5%, against 1.1% for ranchers), concentrated on days
   1-9 at 40-85%. The bridge-wheat result above says that idle cannot be filled
   by finding more work, because `URGENCY_W=0` left task choice **value-blind**:
   it minimises distance and uses tier only to break exact ties, so any cheap
   task added near an expensive one steals from it.

   **That "price, not a tour" proposal was built and rejected, 20 August:
   4-20 in both forms.** See the Routing section above. It converts idle into
   *movement* (42.8% -> 47.5%) while productive actions fall, because the only
   thing a one-step greedy router can do with a value signal is walk toward
   it. The order was backwards: **the tour is the precondition for the price,
   not the other way round.** A per-unit per-day tour is what can actually
   spend "that tile is worth more", by sequencing the expensive tile with the
   cheap ones on the way to it instead of choosing between them.

   **And the tour has now been sized, before building it** (`tour_ceiling.py`).
   Holding the workload fixed and re-routing each unit-day optimally:

   | | per game |
   |---|---|
   | movement actually spent | 2,539 |
   | perfect-routing lower bound | 1,923 |
   | **ceiling on what any tour saves** | **616 (24.3% of movement)** |

   So the greedy router is already within a quarter of optimal on geometry --
   the territories and `URGENCY_W=0` did most of the available work. Worse,
   **most of that saving is unspendable**: 373 of the 616 fall on unit-days
   that *already had idle time*, where finishing the round trip sooner just
   means passing sooner. Only 243 actions/game land on unit-days with no
   slack at all, which at ~$51 a productive action is **~$12k/game, and that
   is an over-estimate on three separate counts** (it reorders with hindsight,
   it ignores growth windows, and it assumes every freed step becomes work).

   Against a bank of ~$100k that is at most a 12% effect for an L-effort
   change, and it is measured against `starter`; the mirror is worth less
   still. **Self-play halves the score, so leads 3 and 4 are the bigger
   pool.** Build the tour for the h2h margin if at all, not for the bank.
3. **Sell timing.** Egg and wheat prices *rise* all season (to ~$92 and ~$47 by
   day 28) because town drain outpaces supply. Nothing exploits the drift.
4. **Opponent modelling.** Both farms are public. Whether the opponent grows
   melon should decide whether our second cycle is worth planting.
5. **A non-mirror evaluation.** `panel.py` exists but only the incumbent
   discriminates — everything beats a cow ranch and a melon IPO 12-0. Better
   sparring partners would have to come from real replays.

---

## Traps specific to this repo

- **`main.py` uses CRLF.** Multi-line string replacement with `\n` silently
  matches nothing. Several edits no-oped this way and the resulting file
  referenced undefined names. Edit by lines, normalise endings, and assert the
  edit applied.
- **Trace before theorising.** Every significant bug here was invisible in the
  score: the farm dying by day 6, geese starving by day 4, five birds pegged at
  `max_held` for ten days, 72% of actions being movement. Use
  `debug_trace.py`, or tally actions by type.
- **Kaggle's CLI:** use `py -3.12 -m kaggle` (2.2.4). The `kaggle.exe` on the
  Store Python 3.9 is 1.7.4.5 and cannot read a `KGAT_` token. A bare `403` on
  submit may just be transient — retry before concluding, it costs nothing.
