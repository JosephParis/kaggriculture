# What has been tried

A log of every experiment run against this agent, kept so nobody re-runs a
losing one. Last updated 20 August 2026.

Read [STRATEGY.md](STRATEGY.md) first for the economics, then this for the
record of what those economics actually bought.

**Current agent: `main.py`** — 6 cows / 2 sheep, 20 melon **cut at day 9**,
strawberry 40, **6 tiles of wheat zoned ahead of melon**, three quadrants,
nearest-task routing. Median **$94.1k** against `starter`, 12/12.

Tuned against **ghosts of our own ladder submissions** rather than `starter`
(`make_ghost.py`, `score_ghosts.py`). Against the 792- and 804-rated builds it
scores **36 of 54** across three independent seed sets, where the build it
replaced scores **3 of 54**. Per-turn p99 is 1.2ms against a 1000ms
`actTimeout`.

The wheat block landed 20 August and is the first change in this file accepted
on **replay evidence** rather than a sweep: ten real losses say the farms that
beat us sell 184 wheat a game to our 44. It is worth **21-3 head to head**.

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
py -3.12 scan_episodes.py <submission_id>              # pull real episodes, keep the losses
py -3.12 analyse_losses.py                             # diff our farm against the one that beat us
py -3.12 optimize.py --games 6 --random 18             # search every acreage knob at once
py -3.12 profile_build.py --replays replays            # read a build's config out of its replays
py -3.12 profile_build.py --agent main.py              # ...and the same fields for this build
py -3.12 make_ghost.py <replay> --out opponents/g.py   # turn a replay into a playable opponent
py -3.12 eval.py --opponent opponents/ghost_804.py     # play our own 804-rated ladder build
py -3.12 score_ghosts.py --knobs K=v                   # win rate vs our own submitted builds
py -3.12 check_forecast.py                             # is the price projection better than guessing?
```

The last two need Kaggle auth (`py -3.12 -m kaggle auth login`) and are the
only tools here that see a real opponent. **Use them before sweeping
anything**: five consecutive sweep-driven candidates were rejected on 20
August, and the replay diff produced an accepted change on the first pass.

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

  **A caveat worth holding, recorded 20 August but not proven.** Five separate
  changes now bank better against `starter` and lose the mirror decisively.
  A clone is maximally correlated with us in exactly the two tempo races that
  never recover -- melon and fertilizer -- so anything that spends money or
  time early hands the clone those races and loses every game. That is a
  reason to suspect the mirror over-punishes, and it is *not* a reason to
  overrule it: when the fourth quadrant was actually tried against the
  recorded farms, both builds won 12-0 and the bank margin it gained buys no
  rating. Until something discriminates on win/loss against a non-mirror
  opponent, the mirror is still the only signal we have.

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
- **Those are base prices, and base prices understate every good the town
  drains.** Measured against realised mid-season prices instead (20 August),
  the ordering is much sharper than the docs have assumed:

  | | units/tile/day | realised | **$/tile/day** | **$/action** |
  |---|---|---|---|---|
  | Cow | 1.5 | $266 | **$399** | ~$100 |
  | Sheep | 1.33 | $190 | $253 | ~$63 |
  | Goose | 2.0 | $60 | $120 | ~$30 |
  | Melon | 0.6 | $182 | $109 | ~$84 |
  | Strawberry | 0.235 | $270 | $63 | ~$63 |
  | Wheat / carrot | ~0.8 | ~$48 | $37 | ~$25 |

  A cow tile is worth **six strawberry tiles**, not the 3.8x the base-price
  figure implies, and it still wins per action even at ~4 actions a day. We
  run twelve animal tiles against ~35 of strawberry. Scaling the herd needs
  ranchers (`GEESE_PER_RANCHER=5`), which pushes the hire target into
  `MAX_HANDS`, which needs land for the displaced strawberry -- the three have
  only ever been tested one at a time, and the hiring leg of that was the void
  measurement above.
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
| 19 | Strawberry 44 → 34, giving wheat a block of its own | **21-3 h2h**, +$3,422 |

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
| ~~Hiring floor of 8 / 10 / 12 hands~~ | ~~3-21, 3-21, 0-24~~ **— void, see below** |
| `TILES_PER_UNIT` 6 / 10 | 1-15, 0-20 |
| Rancher density `GEESE_PER_RANCHER` 4 / 6 | worse, 0-28 at 6 |

> **Correction, 20 August: the hiring-floor row above is not evidence.**
> `MIN_HANDS >= 8` does not produce a farm with too many hands, it produces a
> **bankrupt farm that banks $0**. Hiring is sized with no reference to the
> bank, so the farm pays ~$54/day through the days 0-10 window when it holds
> ~$300 and has no income until the first melon on day 11. It is broke by day
> 9 and never recovers: `BUY_SEED` is issued **twice in a whole game** and
> `BUY_ANIMAL` **not at all**. Nine-plus hires also fill the 10-order market
> queue at hours 0-1, which is what truncates the buys behind them.
>
> This reproduces on the pre-20-August `main.py`, so it is not something the
> recent work introduced. It means the conclusions drawn from that row --
> that extra hands have nothing to do, and that hands and land only pay
> together -- rest on a measurement of a farm that had gone broke.
> **Crew size is an open question again.**

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

### The waste audit: the farm is not leaking, and that closes a direction

Bug-hunting has been the cheap way to find gains here and strategy work the
expensive one, so `audit_waste.py` counts everything the agent throws away.
Per game, against `starter`:

| leak | measured |
|---|---|
| market orders past the 10-per-turn cap | **0** |
| market orders for unsellable items | **0** |
| shed overflow destroyed at end of day | **0** |
| produce unsold at the buzzer | **1** |
| moves that did not move | 26 |
| plants that died before yielding | **3** |
| **unit-actions the environment silently discarded** | **258** |

Only the last was real, and it was one bug: **189 `PLANT` actions a game, every
one "no seed of WHEAT".** Ranchers fill spare animal-zone ground with wheat,
and the crop-hand path checks for seed while the rancher path never did -- so
with feed bought rather than grown, and usually no wheat seed held, ranchers
spent 3.2% of the farm's entire action budget on an action the environment
drops. Fixed by dropping the task at classification, so the router picks the
next-best job rather than the rancher burning its turn.

**It is worth no money.** Discarded actions fall 258 -> 108 and idle falls
24.0% -> 22.9%, and the bank is $94,976 against a $95,344 baseline over the
same 12 paired seeds. The fix is still right -- issuing actions that get
silently dropped is a defect -- but it converts to nothing, which is the
**fifth** independent confirmation that this farm cannot spend spare actions.
It cannot spend them on land, on walking, on a tour, on a learned policy, or
now by reclaiming them from a bug.

The 30 weeds a game are spent strawberry: 36 of 39 deaths are at **age 17**,
which is its natural end of life after yielding at 10, 12, 14 and 16. Three
are premature. Not a leak.

**So the efficiency direction is closed.** Overflow, unsold stock, dropped
orders, dead crops and wasted actions have all been counted and there is
nothing left to reclaim. Whatever is left is strategy, and strategy here has
to get past an evaluation that has now disagreed with the ladder seven times.

### Herd-first: five hypotheses, stuck at $73k, and stopping

Zone sizes now scale with unlocked land (`ZONE_SCALE`), and blocks allocate
out of held ground before locked ground. Both were the fix the trace pointed
at, and neither moves the result:

| attempt | result |
|---|---|
| baseline herd-first | $73.6k |
| bought feed (`FEED_BUY=1`) | $49.1k |
| wheat seed bought first | $73.0k |
| quadrant-first zoning | $46.3k |
| animal purchases gated on feed | $41.1k |
| **zone sizes scaled to held land** | **$73.1k** |
| incumbent | **$95.4k** |

The diagnosis was right as far as it went. Before scaling, the animal zone was
five tiles with **three of them locked**, so the herd had two places to stand;
after, it allocates from held ground first. The herd places properly and the
farm still banks $73k.

**So the placement bottleneck was real and was not the whole story**, and five
traced hypotheses have now failed to close a $22k gap. Each one was plausible,
each was measured, and the honest summary is that the 804 build's opening is
not reachable by rearranging this agent's blocks and buy queue -- something
about how it sequences the first five days is structurally different in a way
the traces have not yet isolated.

All six knobs default to 0 and the incumbent is untouched at $95,344 over 12
paired seeds. `trace_opening.py` is the tool that got furthest and is where a
sixth attempt should start: it reads unit-actions a day, which is the layer
where four money-based hypotheses were invisible.

### Herd-first, traced properly: the herd is bought and never placed

`trace_opening.py` tallies unit-actions a day for the opening and prints the
board beside them, which is the layer the money trace could not see. Days 0-5,
against the incumbent on the same seed:

| | plants by day 1 | idle/day | structures | animals on tiles |
|---|---|---|---|---|
| incumbent | **28** | 11-138 | 0 | 0 |
| herd-first | **8** | 96-184 | 4 | 1 |

And the herd itself, sampled at end of day:

```
day 0  animals-on-tiles 1   shed{SHEEP:3}
day 2  animals-on-tiles 1   shed{SHEEP:2}
day 4  animals-on-tiles 1   shed{SHEEP:1}
```

**Three sheep are bought on day 0 and sit in the shed for days.** One animal
reaches the board in the first eight, no cow is ever bought, and
`consecutive_unfed` never reaches 2 -- so nothing starves and nothing escapes.
The bottleneck is **placement**, and `build=4` on day 0 says why: only four
structures can be built, because the animal zone is the fifteen tiles nearest
the shed, the shed sits at the centre of the board, and eleven of those tiles
are in quadrants we have not bought.

An earlier note here read the animal count oscillating 0,1,0,1 as animals
escaping. That was a sampling artifact -- the board was captured at hour 0,
before the day's placement -- and the escape reading was wrong. Corrected.

This also explains why the quadrant-first ordering failed at $46.3k. It does
put the herd on unlocked ground near the shed, as intended; what it does
instead is push *the crops* onto locked land, because NW only holds ~25 tiles
and the wheat, melon and strawberry blocks then start in NE.

So the real shape of the problem: **with land deferred, the zone sizes have to
shrink to the land actually held and grow as quadrants arrive.** A fixed
fifteen-tile animal zone and a fixed twenty-tile wheat block cannot both fit in
NW, and every fix tried so far has been a re-ordering of blocks whose sizes
were the thing that was wrong.

Four hypotheses tested and rejected on the way, each recorded so nobody repeats
them: bought feed ($49.1k), wheat-first seeding ($73.0k, neutral),
quadrant-first zoning ($46.3k), and gating animal purchases on feed in the shed
($41.1k -- it never opens, because the shed wheat the gate waits for is eaten
by the animals already down).

### Herd-first: three more hypotheses, all wrong, and where it really stops

Continued from the rebuild below, which reached $73.6k against the incumbent's
$95.4k. A day-by-day trace showed the opening spends **$2,700 of its $3,000 on
day 0** and then sits at ~$300 for twelve days with one to three wheat tiles
planted -- so the twenty-tile wheat block that was meant to fund the season
never goes in.

Three fixes followed from that trace. All three failed, and they are recorded
because each is the obvious next idea:

| hypothesis | reasoning | result |
|---|---|---|
| `FEED_BUY=1` | a day-0 herd must eat before our own wheat harvests on day 4 | **$49.1k**, worse -- bought feed drains the cash the herd needs |
| `SEED_WHEAT_FIRST=1` | the seed queue is melon, strawberry, *then* wheat, so the engine is funded last | **$73.0k**, neutral -- seed money was not the constraint |
| quadrant-first zoning | tiles nearest the shed straddle all four quadrants, so the animal zone reserves locked ground | **$46.3k**, much worse |

The third is the instructive one. Grouping the plan by quadrant so early zones
land on ground we already own is plainly sensible and loses badly, because the
animal zone sits nearest the shed **on purpose**: feed comes out of the shed
every day and that walk is paid over and over. Pushing the herd into NW's far
corner to keep it on unlocked land costs more than the locked tiles did.
Ordering stays on shed distance.

**Where this stops.** Three traced hypotheses, three failures, and the gap is
still $73.6k against $95.4k. The opening cannot be reached by re-ordering the
existing purchase queue, which is what all three attempts amounted to. It
needs the sequencing written as its own control flow, and the evidence now
says the binding constraint is not cash, not seed priority and not zoning, so
the next person should trace *what the crew actually does* on days 0-5 before
proposing a fourth fix.

### Herd-first, rebuilt rather than ported: $73.6k against $95.4k

The 804-rated build's whole advantage is its opening -- animals on day 0, its
own wheat for feed, land deferred to days 6 and 8 -- and porting the pieces
one at a time reached only $46k. Rebuilt properly it reaches **$73.6k against
the incumbent's $95.4k**, so it is closer and still losing.

**One real bug was found and fixed on the way, and it is worth keeping.**
Zoning was built from *unlocked* tiles, so `melon_zone =
full_plot[m0:m0+MELON_TILES]` named different physical squares the moment a
quadrant was bought. Harmless when land is bought on day 0, because the board
settles before anything is planted -- and ruinous for any opening that defers
land, because zones then shift under standing crops and a tile watered as
wheat becomes melon ground mid-cycle. `PLANNED_ZONES=1` lays the zones over
the land we *intend* to own. It is worth $46k -> $73.6k to the herd-first
build, and it costs the incumbent $95.4k -> $86.4k, so it defaults to 0: it is
a prerequisite for deferred land, not a gain on its own.

**What still does not work is cash sequencing, and the profile says so
exactly.** Against the 804 target:

| | rebuild | the 804 build |
|---|---|---|
| cows first placed | **day 12** | **day 0** |
| 2nd / 3rd quadrant | day 11 | day 6 / day 8 |
| strawberry / melon acreage | 19 / 5 | 43 / 18 |
| milk sold | 190 | 273 |

Thirteen cows cost $5,200 against a $3,000 opening bank, so the herd cannot go
down at once and everything behind it stalls -- land waits for cash, the
premium blocks never fill, and the crew never ramps. Lowering
`GOOSE_CASH_BUFFER` to let more animals in early is worse, not better:
$5,303 at thirteen cows, because the farm then bankrupts itself exactly the
way `MIN_HANDS>=8` did. That buffer is load-bearing.

So the remaining gap is **not** a parameterisation. The 804 build must grow its
herd progressively against wheat income on a schedule these knobs cannot
express, and reaching it needs the opening written as its own control flow --
buy what this morning's cash affords, place it, let the wheat pay for the
next -- rather than a target count and a buffer.

### Contested rollouts, and a sample-size lesson that voids the table below

The table below concluded that DAgger's rollouts were "the wrong shape"
because they were collected against `starter`, and that the ghost column
showed it. **That conclusion was drawn from eight games and does not survive
thirty-six.**

Re-running DAgger with rollouts against `ghost_804` instead, then scoring the
best checkpoint of each regime over 36 games on three seed bases:

| | vs `starter` | vs ghost_804 |
|---|---|---|
| heuristic | $96,660 | **21/36** |
| DAgger, rollouts vs `starter` | $96,613 | **21/36** |
| DAgger, rollouts vs `ghost_804` | $95,688 | 20/36 |

Three things follow.

**The rollout opponent does not matter.** 21/36 against 20/36 is noise. Both
regimes converge to the same place, which is what DAgger does: it converges to
its expert, and the expert is the same heuristic either way.

**The learned controller is at parity with the heuristic.** Same wins, banks
within $1k. That is the phase's actual goal met -- fine-tuning needs a policy
that can play, and cloning alone gave one that banked $1.

**Eight games is not a measurement.** At n=8 the same checkpoints spread from
2/8 to 8/8; at n=36 they collapse to 20-21/36. The heuristic's "8/8" that the
table below treats as a reference was luck -- it is really 58%. Every
conclusion in that table drawn from an 8-game gap is void, including the one
about rollout shape. `eval_checkpoints.py` defaults are now too small to trust
for anything but a smoke test; use `--games 12 --seeds 3000,5000,7000`.

This repo has a standing rule of 12 games a seat and a documented case of a
6-game panel reversing at 28. It was written for exactly this and I ignored it.

### DAgger: a working controller, and the seventh bank-versus-contest split

The op-head clone banked $1. Predicting the **target cell** instead -- what
the router actually chooses, and what a 10x10 spatial softmax expresses --
fixed that, and DAgger then closed most of the remaining gap. Five
checkpoints, 8 games each over two seed sets:

| checkpoint | vs `starter` | scorer calls | vs ghost_804 | wins |
|---|---|---|---|---|
| heuristic | $95,648 | 0 | $79,787 | **8/8** |
| dagger0 | $95,109 | 65,198 | $78,716 | 7/8 |
| dagger1 | **$103,009** | 65,135 | $80,304 | 2/8 |
| dagger2 | $98,429 | 64,850 | $67,268 | 6/8 |
| dagger3 | $97,782 | 64,836 | $68,335 | 2/8 |
| dagger4 | $100,951 | 64,643 | $77,060 | 5/8 |

**Every row was checked for actually driving.** The scorer is consulted ~65,000
times a batch; a zero there would mean the weights failed to load and the
agent quietly ran pure heuristic, which is how a stale checkpoint once posted
a flawless imitation score. `eval_checkpoints.py` prints the count for exactly
that reason.

Three readings, in order of how much they matter.

**The controller works.** Cloning reached $1; this reaches parity. That was
the actual goal of the phase -- fine-tuning needs a policy that can play, and
$1 was not one.

**Nothing beats the expert where it counts.** Several checkpoints out-bank the
heuristic against `starter` -- dagger1 by $7,361 -- and every one of them wins
*fewer* games against a real opponent. That is the **seventh** time in this
repo that bank and contested outcome have disagreed, and the seventh time bank
was the liar. DAgger converges *to* its expert by construction; it cannot
exceed it, and the bank spread is noise plus fitting to `starter`.

**The rollouts were the wrong shape.** Every DAgger iteration collected states
from games against `starter`, so the policy learned the states an uncontested
game visits. The ghost column is where it shows. Rolling out against
`ghost_804` or a mirror would put the aggregation where the contested
decisions are, and is the obvious next change if this line is continued.

For fine-tuning, **dagger0 is the checkpoint to start from** -- 7/8 against
the ghost and closest to the heuristic it cloned, rather than the higher-bank
ones that trade contested play for it.

### Behavioural cloning: the predictor works, the controller does not

Phase 1 of the cloning-then-fine-tuning plan is built and measured. The
pipeline is `nn_features.py` (board encoding, shared by training and
inference so the two cannot drift), `nn_dataset.py` (replays -> arrays),
`train_bc.py` (JAX, CPU) and `nn_policy.py` (numpy inference).

**Scope: only unit control is learned.** Hiring, land, animals, seeds and
market orders stay heuristic -- they are a handful of decisions a turn rather
than a per-cell field, they are tuned, and leaving them out keeps the learned
part small enough to fine-tune. The board is encoded once a turn into 41
planes and each unit reads the cell it stands on, which turns a ~`20^11`
joint action space into eleven independent 18-way choices.

**As a predictor it works.** A 48-channel, 3-block residual CNN, 143k
parameters, held out *by replay*:

| | held-out accuracy |
|---|---|
| majority class | 16.5% |
| linear probe, 43 hand features | 44.8% |
| **residual CNN, 4 epochs** | **65.1%** |

Numpy inference matches the JAX reference to 9.5e-06 and runs in 3.2ms a
turn against a 1000ms budget, so deployment is not a constraint.

**As a controller it fails, and the failure is the textbook one.** Handed the
crew outright, the cloned policy banks **$1**. `PASS` is legal on every tile,
so the policy's PASS overrides a productive heuristic op, and past that it is
plain distribution shift: 65% per-action accuracy compounds over 720 turns,
and the first mistake moves the agent into board states no demonstration
contained.

**The safe half is a no-op.** `LEARNED_UNITS=1` lets the policy act only where
the heuristic would PASS -- filling idle, which is worth nothing by
definition, so a wrong guess costs a turn already being thrown away. It does
what it says: `PASS` goes to **zero**. It changes nothing else.

| | bank vs `starter` | ghosts |
|---|---|---|
| heuristic | $95,424 | 8/12 |
| idle filled by the policy | $95,424 | 8/12 |

That is the **fourth** independent confirmation that this farm's idle is
structural rather than a scheduling failure. It cannot be spent on land
(bridge wheat, 0-24), on walking (priced routing, 4-20), on a tour (sized at
~$12k, mostly unspendable), and now not on learned actions either.

**Where that leaves fine-tuning.** The plan was clone-then-PPO, and the clone
is not a viable starting point: fine-tuning from a policy that banks $1 is
much closer to RL from scratch, which the feasibility work already ruled out
on this hardware. The standard fix applies and is cheap here -- **DAgger**:
roll the current policy out, label the states it actually visits with the
heuristic as the oracle, retrain, repeat. Unlike the replay corpus, that data
is unlimited (227 episodes/min) and it is drawn from the policy's own state
distribution, which is exactly what cloning from expert-only states lacks.
That produces a robust controller matching the heuristic, which is the
starting point PPO needed in the first place.

### The ghost panel does not predict the ladder (21 August)

Two builds tuned against ghosts came back rated **672.8** and **600** against
the hand-built lineage's **801.7** and **804.3**. The panel said they were
better by a wide margin; the ladder says they are much worse.

The reason is the caveat that was recorded when the panel was built and should
have been weighted harder: **a ghost replays a fixed tape and cannot react**,
so tuning against one rewards exploiting fixed behaviour -- melon timing above
all -- and a live opponent adjusts. Two compounding errors: the tuning was
also applied to the 18 August lineage, which rates 581-628, so it was
polishing the weaker of the two architectures in the repo.

**Ghost win rate is a filter, like bank was.** It is still the only way to
play a submission whose source is gone, and it is still worth running -- but
"36/54 against the ghosts" is not a claim about the ladder, and this file
should not have implied it was.

### Reinforcement learning: assessed, and not the first move

Measured on this machine on 21 August, since the question is entirely about
budget rather than about whether the method works in principle:

| | measured |
|---|---|
| env, one worker | 356 steps/s |
| env, ten workers | 2,720 steps/s (227 episodes/min, ~235M steps/day) |
| joint action space | ~`20^11` = 2x10^14 per turn |
| labelled pairs per replay | **13,814**, both seats, 16 distinct ops |
| available across 12 submissions | ~6.6M pairs |
| hardware | ARM64, 12 cores, **no CUDA**, JAX on CPU, no torch |
| inference budget used | 1.3ms of 1000ms |

Rollouts are not the bottleneck; the gradient work is. PPO runs that reach
strong play on comparable games (Lux AI, Halite) spend 10^8-10^9 steps *with*
GPUs. **From-scratch RL is not viable here** in the time left.

**Behavioural cloning is viable, and was probed rather than assumed.**
`bc_probe.py` fits a plain multinomial logistic regression on 43 cheap
per-unit features, held out *by replay*:

| | held-out accuracy |
|---|---|
| majority class (`WEST`) | 15.8% |
| linear model | **44.8%** |
| its `WATER` recall | 89.4% |
| its `SOUTH` recall | 27.8% |

A linear model nearly triples the baseline, and the split across classes is
the useful part: productive acts are predictable from local state, movement is
not, because a direction encodes a *destination* a board-wide encoder could
see and local features cannot. There is real headroom.

**But cloning cannot exceed its demonstrations**, and ours are opponents rated
600-800, not the leaders at ~3190. So it is a tool for a specific job --
recovering the 804 build whose source is gone, and mining what beat us -- not
a strategy.

**The first move is not machine learning.** The largest measured gap is that
the 804 build places animals on **day 0** and this one cannot place a cow
until melon money lands on **day 11**; a cow yields eight days after
placement, so ours milks from day 19 against their day 8, which is the whole
of the 146-vs-273 milk gap. That spec is already recovered by
`profile_build.py`. Full write-up: the RL feasibility report artifact.

### Reading the market: a forecast, and what it is worth (21 August)

Everything above this point is a farm that decides its whole season on day 0.
The acreage, the herd split and the melon cutoff are constants fitted by
sweeps, and none of them looks at what the market is doing or at what the
other farm has in the ground. `main.py` now carries a copy of the
environment's pricing so it can value a *future* harvest.

Nothing about that price is unknown:

- **The price function is exact.** `_price_at` reproduces `market_price` on
  **4,000 of 4,000** random inventories. The parameters are duplicated rather
  than imported, since a submitted agent has no `kaggle_environments`.
- **The drain is exact, not an average.** `obs["town"]["unlocked_shops"]`
  lists shop *instances* including repeats, so `_drain_rates` computes this
  game's real demand rather than the expectation over the random draw.
- **Both farms' pipelines are visible.** `obs["farms"]` is public, so
  `_pipeline` counts the units already in the ground on either side --
  their melon ripening is observable days before it lands.

`_projected_price(view, item, days)` puts those together:
`inventory - drain x days + our pipeline + their pipeline`.

**The forecast is real, and it was measured before being trusted.**
`check_forecast.py` records the projection made on day *d* for horizon *h*,
then compares it against the price actually seen on day *d+h*, and scores the
naive "today's price holds" alongside as the baseline to beat:

| | h=4 | h=10 | h=16 |
|---|---|---|---|
| MELON, projected vs naive | 17 / 19 | 33 / 48 | **37 / 62** |
| STRAWBERRY | 19 / 19 | 22 / 46 | **36 / 71** |
| WHEAT | 1 / 3 | 4 / 9 | 8 / 14 |

It beats carry-forward on **14 of 15** item/horizon pairs and roughly halves
the error at long horizons, which is exactly where a planting decision needs
it.

**Accepted: the herd composition is now a market read, not a constant.**
Cow and sheep both stand on a PASTURE, so trading one for the other costs no
structure and no action -- which is what makes it cheap enough to redecide
every turn. Only unplaced tiles switch; an animal already grazing is what it
is, and geese are never substituted because a COOP is a different building.

The two curves diverge hard enough to be worth watching: wool is `sq` above
I0 with T=105, milk `linear` with T=122, and the town drains milk 19/day
against wool's 13. A pasture zoned for milk while the market already carries
400 units of it is worth **$22/day**; the same tile as wool is worth **$348**.

| | seed 3000 | 5000 | 6000 | total |
|---|---|---|---|---|
| fixed 6 cows / 2 sheep | 11/18 | 16/18 | 9/18 | 36/54 |
| **adaptive** | **12/18** | 16/18 | **10/18** | **38/54** |

It also banks more ($57.5k -> $74.6k on seed 5000) and **makes `N_COWS` and
`N_SHEEP` irrelevant** -- 6/2, 4/4 and 0/8 all converge to the same result,
which is the point. Two hand-fitted constants are now one rule. Per-turn p99
is 1.34ms against the 1000ms `actTimeout`.

**Rejected: adaptive crop choice** (`ADAPTIVE_CROP`, defaulting to 0). Letting
the same projection pick the crop per tile, with `MELON_LAST_PLANT` relaxed so
it could decide the second melon cycle itself, scored **13/18 on seed 3000 and
7/18 on both held-out sets** -- 27/54 against the adaptive herd's 38/54. The
seed-3000 gain was noise, and it would have shipped had it not been validated
out of sample. Worth keeping in mind that the rule *approximately rediscovers*
the day-9 cutoff on its own (10/18 where the fixed cutoff gets 11/18), so the
forecast is sound and it is the per-tile substitution that is not.

**The opponent read is worth about a game.** Ablating it -- `RIVAL_WEIGHT=0`,
which prices as if the other farm did not exist -- costs 12/18 -> 11/18.
Small, but it is the first thing in this repo to make issue 09 pay anything.

### Tuning against our own submissions, and an intransitivity

`make_ghost.py` made the 792- and 804-rated builds playable, so `optimize.py`
was pointed at them with **games won** as the objective instead of bank. That
found, in order: melon 24 -> 20, strawberry 34 -> 40, herd 8/4 -> 6/2,
`MELON_LAST_PLANT` 19 -> **9**, and 6 tiles of wheat zoned *ahead* of melon.

| | vs the three ghosts, 3 seed sets |
|---|---|
| the build this replaced | **3 / 54** |
| current `main.py` | **36 / 54** |

`MELON_LAST_PLANT=9` is the sharpest single move and **this file recorded it
as "$8k worse"** -- true on bank against an opponent that does not contest
melon, wrong against one that does. The 804 submission's own note reads "melon
second cycle cut at day 9 ... 63-1 vs previous build". Bank picked the wrong
side seven times on 20 August; here melon 24 banks $76.1k and wins 3 of 18
while melon 20 banks $64.8k and wins 10.

**But the ranking is intransitive, and that matters more than the tuning.**
Measured head to head:

- the wheat-block build beats the 18 August build **21-3**
- the 18 August build beats this one **32-16**
- this one and the wheat-block build are **13-11**, i.e. level

A > B > C with A = C. That is not noise, it is what a shared market does: each
build's value depends on what the other one contests. **So no single h2h is a
ranking, and "beats `main.py`" is not the same claim as "is better".** A
candidate has to be scored against a panel.

The honest caveat on the panel used here: a ghost replays a fixed tape and
cannot react, so some of that 36/54 is likely exploiting melon timing a live
opponent would adjust. The ghosts are still the only way to play the builds
that actually rate 792 and 804, and the margin over three independent seed
sets is far too large to be seed noise.

### Reconciling this repo with the ladder submissions (20 August)

The submissions list has twelve entries, not the five recorded below, and a
19-20 August lineage rates **752-804** against this repo's 581-628. There is
no API for downloading your own submitted agent and the replay JSON carries no
source, so the only way to see that build is to read its configuration back
out of its behaviour. `profile_build.py` does that, and prints the same fields
for a local agent so the two can be diffed line for line.

| | this repo (`main.py`) | the 804 build |
|---|---|---|
| **animals placed** | **day 11-12** | **day 0** |
| herd | 8 cow / 4 sheep | 13 cow / 2 sheep, and sometimes 5/11 |
| wheat acreage | 2 | **20** |
| strawberry / melon | 34 / 24 | 43 / 17-21 |
| hands, days 0-11 | 6,6,6,6,6,6,6,6,6,6,6,9 | **4,4,4,5,5,5,4,7,8,11,10,11** |
| max hands | 9 | 12 |
| 2nd / 3rd quadrant | day 0 / day 10 | **day 6 / day 8** |
| milk sold | 146 | **273** |

**The headline is the opening.** This build queues `BUY_LAND` ahead of
`BUY_ANIMAL`, so day 0 spends $1,000 on NE and the rest on melon seed, the
farm is broke by day 1, and the first cow is not placed until the melon money
arrives on **day 11**. A cow first yields eight days after placement, so ours
starts milking on day 19 against their day 8 -- which is the whole of the
146-versus-273 milk gap.

**None of it ports.** Every piece was tried against this build:

| ported piece | result |
|---|---|
| `GOOSE_START_DAY=0` (herd on day 0) | **$46k**, and $31k combined with late land -- catastrophic |
| herd 13/2, 11/4, 13/4 | all below 8/4 |
| strawberry 24 (wheat 20) | $99.3k against $104.9k |
| `LAND_START_DAY=6` (land day 6) | +$464 on bank, **6-18 head to head** |

The day-0 herd starves here because this build *buys* its feed and has no
income until melon; the 804 build affords a day-0 herd precisely because it
grows twenty tiles of its own wheat and sizes its crew off the herd. The
pieces only work together. **It is a different architecture, not a different
parameterisation, and it has to be rebuilt rather than ported.**

`profile_build.py` gives the target to rebuild against, and the numbers above
are the specification: herd down on day 0, own wheat, crew ramped 4 -> 11
across the first ten days, land at days 6 and 8, melon in on day 4.

**We can now play our own ladder build.** `make_ghost.py` turns a replay into
a replayable action tape, the same trick `opponents/` already uses for real
rivals, so the 804 build -- which exists only as a submission -- can be played
against directly. `opponents/ghost_804.py` is episode 95157730, seat ours.

The result settles the submission question: **`main.py` loses 0-8 to it**,
$66,974 against $73,919 over eight seeds. This repo's build is genuinely
weaker than what is already on the ladder, measured rather than inferred from
ratings, and the ghost is *handicapped* -- a tape cannot react and is replayed
on boards it never saw, which is why it banks $73.9k here against the $82.4k
it originally scored. **Submitting this build would be a regression. Do not.**

The ghost is also a far better search signal than `starter`, so `optimize.py`
takes `--opponent` and switches its objective from bank to games won when
given one.

Rebuilding the herd-first architecture was attempted and is not close.
`HERD_FIRST` (buy the herd before the land) and `WHEAT_FIRST_TILES` (give
wheat ground ahead of melon, since with land delayed the melon zone otherwise
swallows all 25 tiles of NW) are both in `main.py` defaulting to 0. The best
configuration found -- herd first, land day 6, own feed, wheat 8, melon 18 --
banks **$46k against the incumbent's $104k**. The 804 build's descriptions
name several further pieces this repo does not have (crew sized off the herd,
delivery at 8, melon cut at day 9, adaptive cow/sheep from live prices,
endgame feed liquidation), and the opening alone does not carry it.

Two real bugs were fixed along the way.

**`BUY_LAND` never decremented the running balance**, so every animal and seed order later in the same turn believed it
had $1,000-$2,000 more than it did, against the explicit intent recorded in
accepted change 14. Fixed. It is behaviour-neutral at the current defaults
(land is only bought when cash is plentiful) and it matters the moment land
and herd compete for the same day, which is exactly what the 804 build does.

**Hiring read no balance at all**, which is why `MIN_HANDS>=8` banked $0 and
why the "hiring floor" row above is void. `_hire_target` now caps the
morning's bill at `HIRE_BANK_SHARE` (0.25) of the bank -- a share, not a fixed
reserve, because a fixed reserve throttles the healthy case instead of
catching the sick one: against an early bank of ~$300 a $400 buffer forces the
crew to one hand and costs $9k. The guard is always on and leaves the default
untouched ($104,446 either way, six hands costing $20 against a $120
balance). `MIN_HANDS=8` now banks **$94,861 and wins 6-0** instead of $0 --
still worse than the default, but for a real reason rather than bankruptcy.

### What the replays actually said (20 August)

Open lead 1 -- "replay analysis of a loss to a strong opponent" -- has been the
top of this list since 18 August and was finally run. `scan_episodes.py` pulls
an episode list, downloads the replays and keeps the losses;
`analyse_losses.py` diffs our farm against the farm that beat us. Replays carry
**both** farms in full plus both action dicts, so none of this is inferred.

Twenty episodes of submission 55647314: **10W 10L**, which is the mid-ladder
record the rating implies. Averaged over the ten losses, units sold per game:

| product | us | winner | diff |
|---|---|---|---|
| **WHEAT** | 44 | **184** | **+140** |
| STRAWBERRY | 141 | 177 | +36 |
| CARROT | 0 | 32 | +32 |
| WOOL | 113 | 122 | +9 |
| MELON | 99 | 101 | +2 |
| MILK | 228 | 171 | −57 |
| FERTILIZER | 300 | 157 | −143 |

**We win the premium races and lose on staples.** We out-produce the field on
milk and fertilizer -- the two goods this repo has spent the most effort on --
and sell a quarter of their wheat. Wheat is the **largest town drain in the
game at 31/day**, its curve is `log` so it never crashes at any volume we can
reach, and its price climbs $26 -> $51 across the season. We had priced it at
its $25 base, concluded it earned ~$11/action, and dropped it entirely once
feed was bought. At the realised price it is roughly twice that.

Acting on it is accepted change 19 above: strawberry 44 -> 34, and the ten
freed tiles fall back to wheat. **21-3 head to head.**

**This is not bridge wheat.** That put wheat on melon and strawberry ground and
desynchronised the premium blocks, and lost 0-24. This gives wheat ground of
its own and never touches the premium blocks' timing. The distinction is the
whole result: it was never "wheat is worthless", it was "do not borrow premium
ground".

Two more things the replays turned up:

- **The submitted agent issues 542-885 `SELL COW` / `SELL SHEEP` orders a
  game, and every one is silently dropped.** `PRODUCTS` in the environment
  source does not include animals, so the order costs a slot in the
  ten-per-turn queue and does nothing. It is *nearly* harmless -- the queue
  only reaches its cap on ~21 turns a game, and only 2-3 of those had a dead
  order displacing a real one -- so it is a tidiness bug, not the gap. Worth
  fixing, not worth crediting. `main.py` in this repo already guards it with
  `item in ANIMAL_SPEC`; the submitted lineage does not.
- **The ladder work has diverged from this repo.** There are **twelve**
  submissions, not the five this file records. The 18 August builds rate
  581-628, but a lineage submitted on 19-20 August rates **752-804**, peaking
  at 804.3 (55637915, "wheat 6->20 on the herd-first crew"). Their
  descriptions name a herd-first opening, a crew sized off the herd, land on
  day 6, melon on day 3, delivering at 8 rather than 14, and an adaptive
  cow/sheep choice off live prices -- **none of which is in this repo**, and
  several of which this file records as losing. Whatever is in `main.py` here
  is not what is rating 804 on the ladder.

  Note in particular that 55617318 is "deliver at 8 not 14: 45-19 vs previous
  build" while the Logistics table below records `DROP_THRESHOLD` 5/8 losing
  to 14, and 55616633 is "melon second cycle cut at day 9 ... 63-1" while the
  Crops table records a day-9 melon cutoff as $8k worse. Those conflicts are
  real and unresolved: they were measured on different builds.

### Searching the whole allocation at once

The acreage constants here were each fitted alone with the others held still,
which is the wrong shape of answer when the goods share tiles, crew and
market. Three attempts at fixing that, in order of how much they were worth:

**1. A steady-state surrogate (`allocate.py`) -- failed.** Ranked known
results backwards four times in five. Retired; see below.

**2. A day-indexed surrogate (`season_model.py`) -- calibrated, still cannot
rank.** It tracks a bank, a planting date per tile and an action budget for
both farms against one market. Absolute bank comes out close: **mirror $85.0k
against a real $77.9k**, 9% high. Ranking is a coin flip, **5/10** on
`--validate`, because it over-produces melon by 48% (276 units against a
measured 187) -- it replants melon on a clean 11-day cycle the crew never
achieves, and melon is a race whose value is almost entirely timing. Closing
that with a yield fudge factor would be fitting rather than modelling, so it
was left. `py -3.12 season_model.py --validate` re-runs the check.

> **Worth knowing: the "$18-25k mirror" figure in STRATEGY.md is stale.** It
> describes the old goose build. This agent's real mirror bank is **$77,904**
> median over 6 paired seeds. Using the old number as a calibration target
> sent the day-indexed model chasing a value four times too low.

**3. Searching the real environment (`optimize.py`) -- the trustworthy one.**
No surrogate is needed: we own an exact model of the season and a game costs
~35 seconds. What was missing was a search that moves every knob *together*.
Coordinate descent over cows, sheep, melon and strawberry, on paired seeds,
**converged immediately on the incumbent** -- `{COW 8, SHEEP 4, MELON 24,
STRAWBERRY 34}` at $104,446, with no single-axis move improving it. So the
one-at-a-time fitting did land on a joint local optimum, which is worth
knowing and was not obvious.

Coordinate descent cannot see a move that changes several goods at once,
which is exactly where interaction lives, so `--random N` also samples
allocations that move every axis simultaneously. **Eighteen such samples, and
none beat it** -- the best was $99,512 against the incumbent's $104,446:

| allocation | bank |
|---|---|
| **incumbent 8/4, melon 24, strawberry 34** | **$104,446** |
| 4 cows / 8 sheep, melon 16, strawberry 28 | $99,512 |
| 8/6, melon 24, strawberry 22 | $97,342 |
| 4/8, melon 24, strawberry 40 | $94,585 |

So the current allocation is a genuine local optimum in the joint space, not
just along each axis. **The one-at-a-time fitting was the wrong method and it
happened to land on the right point.** That is worth knowing in both
directions: the acreage is not where the remaining score is, and the next
person to sweep a single knob should expect to find nothing.

Two caveats on that conclusion. It is a *local* optimum over the ranges in
`AXES` -- cows 4-12, sheep 0-8, melon 16-32, strawberry 22-40 -- and the
strawberry curve has already proved non-monotonic once, so a genuinely
different region (no melon at all, or a herd twice this size on four
quadrants) is not ruled out. And it is measured on bank against `starter`,
which is the filter, not the objective.

Bank against `starter` is the search signal because it is cheap and dense.
**It is a filter, not the objective** -- five candidates on 20 August banked
better and lost the mirror -- so `optimize.py` prints "NOT a result yet" and
refers the winner to `h2h.py`.

### The steady-state surrogate, and why it does not work

Every acreage constant here was fitted alone with the others held still --
melon swept to 24, strawberry to 44 then 34, the herd to 8/4, wheat the
leftovers. That is the wrong shape of answer, so `allocate.py` solves the
portfolio directly: greedy marginal allocation over all eight goods against
the environment's own price function, with the town drain and the opponent's
supply priced in.

**It fails retrodiction and must not be used to allocate.** Scored against six
allocations whose head-to-head result is already known, it gets four of five
comparisons backwards -- it ranks the 12-goose build measured at **0-24**
*first*, and the current best *fifth of six*. Charging the feed a 20-goose
farm would really eat moved the numbers and not the ordering. The one
prediction it was tested on live, a diversified low-melon build, lost
**0-24**.

The reason looks structural. Everything that has decided anything in this repo
is **temporal**: bridge wheat lost because wheat on melon ground pushed the
premium blocks four days late, the season turns on the day-11 plant-out when
the first melon money lands, and melon is a race where the first seller takes
~$217 and the second takes $1. A model that multiplies units per day by a
price has no representation of tempo, so it cannot rank builds that differ in
it -- which is most of them.

Three things it did establish, all of which stand:

- **The expected town drain, derived rather than measured**, reproduces the
  empirical table exactly: wheat 31/day, carrot and milk 19, strawberry 25,
  tomato/egg/wool 13, melon 1, fertilizer 0. Computed from `SHOPS` and
  `TOWN_CENTER_PRODUCTS` in about ten lines, where the original took a season
  of tracing.
- **The premium price curves are far steeper than this file has assumed.**
  Milk, strawberry and melon hit the $1 floor just **200 units above
  `MARKET_I0`**; wheat and egg are `log` with T=400 and T=332 and barely move
  at any volume either farm can reach. That is the mechanism behind the replay
  finding above -- staples survive a contested market and premium goods do
  not -- and it is worth more than the allocator that produced it.
- **Actions bind before tiles do.** The solver stops around 52 of 71 tiles,
  which matches the farm sitting two-thirds planted and supports "actions are
  the currency" over "buy more land".

### Crew and land, retested 20 August

| Idea | Result |
|---|---|
| **Hire to the work and the cash that exist** (`HIRE_TO_WORK`) rather than to tiles owned | **worse**: $92.7k, $94.2k, $51.0k across three formulations, against $100.9k |
| **The fourth quadrant** (`MAX_LAND=3`), retested at current strength | bank up against 3 opponents of 4, **0-24 in the mirror**, and **12W-0L either way** against every recorded opponent -- *not* a validated gain |

Both followed from the bug above: if the hiring evidence is void, crew size
and land are open, and they are the pair the docs say "buy each other".

**Hiring to work does not work.** The crew is sized off `len(full_plot)` --
every tile owned, whether or not anything can be done with it -- which is why
nine hands tend twenty-one planted tiles on day 1 and idle 85%. Sizing instead
off tiles that are actually growing or grazing, plus bare ground we hold seed
for, loses $6.7k; adding ground we can *afford* seed for loses $50k. The
reason is that hiring runs at hour 0-1 and the crew lasts the day, so a count
taken in the morning under-hires for **day 11**, when the melon money lands
and the farm plants out every bare tile at once. That day must not be slowed
-- the same lesson bridge wheat taught. The knob is kept, defaulting to 0.

**The fourth quadrant is the closest thing to a gain found all day, and it
still does not qualify.** Against `starter` it is +$4,397 over 12 paired
seeds. Against the recorded farms in `opponents/`, 12 games each on seeds
2000-2011:

| | `main.py` | `MAX_LAND=3` |
|---|---|---|
| Floth | $95,659 | **$102,728** |
| Piotr Gabrys | $92,145 | **$94,399** |
| Pratik Vadher | **$83,685** | $80,095 |

Better against three opponents of four, worse against one. But **both builds
go 12W-0L against all three recorded farms**, so by the ladder's own metric
they are indistinguishable there, and coin margin buys no rating. The only
win/loss evidence that exists is the mirror, and that is **0-24**. On the
measure that scores, the retest is neutral-to-negative. `MAX_LAND` stays 2.

### Sell timing and the market (issue 10)

| Idea | Result |
|---|---|
| **Meter the premium goods** (`SELL_METER`) -- sell `linear`/`sq` goods a slice a turn instead of dumping each wave | **8-16**, on a bank that barely moves ($99,851 -> $99,870) |
| **Replant melon ground as strawberry once melon dies** (`MELON_SWITCH`) | **2-22**, while banking **+$5,254** vs `starter` |

The premise of issue 10 was "dump `log` goods, meter `linear`/`sq` goods".
**The metering half is unnecessary, and the trace says why.** Midday market
prices, seed 1000, against `starter`:

| day | 0 | 9 | 12 | 18 | 24 | 27 |
|---|---|---|---|---|---|---|
| MILK (base 160) | 169 | 211 | 234 | 268 | 286 | **297** |
| STRAWBERRY (base 120) | 128 | 169 | 193 | 243 | 285 | **300** |
| WOOL (base 200) | 206 | 221 | 223 | 226 | 189 | 158 |
| WHEAT (base 25) | 26 | 31 | 34 | 42 | 47 | **50** |
| FERTILIZER | 100 | 100 | 100 | 88 | 74 | 67 |
| MELON (base 250) | 256 | 271 | 174 | 184 | **4** | 13 |

Milk and strawberry finish the season at **1.9x and 2.5x their base price**,
because the town drains them (19/day and 25/day) faster than two farms supply
them. There is no glut to meter.

**And metering is not merely unnecessary, it loses: 8W 16L over 12 paired
games a seat**, on a bank that moves by almost nothing. This was first written
up here as a "no-op" on the strength of the bank alone, which is exactly the
mistake this file exists to prevent -- the bank is a filter, `h2h.py` is the
objective, and they disagreed again.

The mechanism is that **the town drain is a race, not a reservoir**. The town
center takes one of each product every 24 turns and each shop instance one
every 4; that demand is consumed by whoever sells into it first. Holding stock
back to protect a price we were never going to crash just means the opponent's
identical goods clear the same window ahead of ours. Selling immediately is
right for *everything* -- not only for the `log` sinks and the two goods that
never recover, which is all the original issue claimed.

**This also retires the `STRATEGY.md` absorption table for sell decisions.**
That table computes cumulative revenue into a *fresh* market with no drain,
and it says milk floors by unit 50; we sell 292 units at a realised ~$266.
For any good the town drains it is wrong by a factor of four. Only melon and
fertilizer, which the town drains 1/day and 0/day, behave the way it predicts.

The second idea followed from the same trace. Melon is the one good that does
crash -- $271 on day 9, $174 on day 12, **$4 by day 24** -- because our own
first harvest lands on day 10-11 and nothing drains it afterwards. So the
melon block should arguably stop being melon once melon is dead, and become
strawberry, which is climbing. This is *not* the day-9 and day-13 melon
cutoffs already recorded above: those stopped planting and left the ground
bare, this changes what goes into it.

It banks well and loses badly. Swept on bank, six paired seeds:

| threshold | median bank |
|---|---|
| 150, 160, 170 | $100,890 (never fires -- melon holds ~$175 until day 21) |
| **180** | **$106,144** |
| 190, 200, 220 | $102,746 |
| 260 | $45,940 (kills melon outright) |

At the best threshold, head to head: **2W 22L 0D**.

**The mechanism is the one bridge wheat already taught us, and this is the
third measurement of it.** `starter` does not contest melon, so against it the
melon we give up is melon nobody takes and the swap reads as free. In a mirror
the melon we do not grow is melon the opponent sells at ~$217 into a market
that never recovers. Melon acreage is load-bearing in a way the bank against
`starter` structurally cannot show.

The general rule now has three independent confirmations: **any change that
trades melon away banks better against `starter` and loses the mirror.**
Bridge wheat (0-24), priced routing (4-20) and this (2-22) all did it.

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

1. ~~**Replay analysis of a loss to a strong opponent.**~~ **Done, 20 August
   -- and it was worth more than everything else on this list put together.**
   See "What the replays actually said" above. It produced the only accepted
   change of the day (wheat block, 21-3) after five sweep-driven candidates
   had all been rejected. The tooling is `scan_episodes.py` and
   `analyse_losses.py`; re-run it after any structural change.

   **The gap was not execution.** Movement is 42.8%, the router is within a
   quarter of optimal, and none of that mattered: the farms beating us simply
   sell four times the wheat. Next pass should look at *carrot* on the same
   grounds -- the field sells 32 a game to our zero, the town drains it
   19/day, and its curve is `sqrt` -- and at the herd-first opening the
   19-20 August submissions describe.
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
3. **Sell timing -- answered, 20 August, and it goes the other way.** The
   drift is real (see the price table above) but it is not ours to exploit:
   this build grows no wheat and keeps no geese, so egg and wheat are not
   what we sell. What we do sell already prices above base, because the town
   drains milk, wool and strawberry faster than two farms supply them --
   and metering those goods *loses* 8-16, because the drain is a race and
   holding stock lets the opponent clear the window first. The one good that
   genuinely crashes is melon, and every attempt to spend less of the farm on
   melon has lost the mirror. **The incumbent's dump-everything-immediately
   rule is already correct.**
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
