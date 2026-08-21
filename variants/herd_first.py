"""
Kaggriculture agent: buy labour, buy land, run geese, grow wheat to feed them.

The single-farmer wheat baseline scored ~$6,000. What was missing:

  1. **Labour is nearly free.** A hire costs `fib(n)` for the n-th hire of the
     day and resets every morning, so eight hands cost $54/day for 192 extra
     actions -- $0.28 an action against roughly $11 of return.
  2. **Nobody needs to walk to the shed to store things.** `_end_of_day` drops
     every unit's inventory into the shed automatically. Units stay in the
     field and only make a shed trip when the 100-item shed cap is at risk, or
     when they need to fetch feed.
  3. **Watering every day is a waste.** A plant dies only after *two*
     consecutive dry days, and watering only adds yield inside the bonus
     window, so wheat wants watering on days 0, 2, 3, 4 -- not day 1.
  4. **Geese dominate crops per tile.** A goose is $300 plus one BUILD_COOP and
     returns roughly $140/day for ~3.5 actions: two eggs, because CARE banks a
     bonus that pays out on the next day's production, plus one fertilizer.
     A wheat tile returns about $16/day. Eggs are a `log` sink that never
     crashes, and fertilizer starts the day after placement, before the first
     egg does.

Land and labour buy each other, and both exist to serve the geese: wheat is
grown mainly as feed and sold only above the reserve.

Units hold a **fixed territory** for the day rather than chasing whatever tile
is most urgent globally. Re-deciding globally every turn made units oscillate
and the farm filled with weeds. The tiles nearest the shed are reserved for
coops, so feed trips stay short, and the units working them are ranchers for
the whole day.

Everything is greedy and per-turn. `actTimeout` is 1 second across 720 turns,
so there is no room for search.

Policy constants can be overridden by `KAG_*` environment variables so
`sweep.py` can tune them without editing this file; the defaults are what gets
submitted. See docs/STRATEGY.md for the economics behind the numbers.
"""
import math
import os
import random as _rand

BOARD = 10
SHED_ACCESS = [(4, 4), (5, 4), (4, 5), (5, 5)]

# Copied from the environment source. A submitted agent cannot import
# kaggle_environments, so these are duplicated rather than referenced.
# Per crop: seed cost, the age to harvest at, and the watering window that
# actually adds yield. Watering outside the window only keeps the plant alive.
#
# Melon is the premium play. Watering ages 6-10 takes it from 1 unit to its cap
# of 6, and first_yield_day is 10, so it harvests the same day it maxes out --
# ages 11 and 12 add nothing and only risk the decay that starts at 13. Ten
# actions for 6 melons at ~$217 is ~$130/action, against wheat's ~$11.
# `units` is the yield a finished tile carries and `actions` the whole cycle
# including the walk-free actions (plant, waterings, harvests); together they
# price a planting at dollars per action, which is what PRICED_ROUTING ranks on.
CROP_SPEC = {
    "WHEAT": {"seed": 10, "harvest_age": 4, "window": (2, 4),
              "units": 4, "actions": 7},
    "MELON": {"seed": 80, "harvest_age": 10, "window": (6, 10),
              "units": 6, "actions": 13},
    # Ongoing: produces at ages 10, 12, 14, 16 and then decays, so it is
    # harvested repeatedly and never replanted. Watering earns no yield bonus
    # on an ongoing crop, so it is watered only to keep it alive. The town
    # drains strawberry 25/day, more than any other product, which is why the
    # price holds despite a curve that would otherwise floor it by unit 60.
    "STRAWBERRY": {"seed": 100, "harvest_age": 10, "window": (99, 0),
                   "ongoing": True, "units": 4, "actions": 13},
}
WHEAT_SEED_COST = CROP_SPEC["WHEAT"]["seed"]
WHEAT_MAX_YIELD_DAY = CROP_SPEC["WHEAT"]["harvest_age"]
# Per animal: cost, the structure it stands on, and how much product it can
# hold unharvested. CARE banks +1 a day and pays out on the next scheduled
# production, so an animal on interval i yields (1 + i) units every i days.
# Times the base price, that is what the tile is really worth:
#
#   SHEEP  1.33 wool/day @ $200 = $267/day, payback 1.9 days
#   COW    1.50 milk/day @ $160 = $240/day, payback 1.7 days
#   GOOSE  2.00 eggs/day @  $50 = $100/day, payback 3.0 days
#
# Geese are the worst of the three. Units per day is the wrong metric -- an
# egg is worth a third of a milk. The premium prices hold up because town
# shops drain milk 19/day and wool 13/day, well above what one farm makes;
# only melon (1/day) and fertilizer (0/day) actually stay crashed.
ANIMAL_SPEC = {
    "GOOSE": {"cost": 300, "structure": "COOP",    "build": "BUILD_COOP",
              "product": "EGG",  "interval": 1, "max_held": 4},
    "COW":   {"cost": 400, "structure": "PASTURE", "build": "BUILD_PASTURE",
              "product": "MILK", "interval": 2, "max_held": 6},
    "SHEEP": {"cost": 500, "structure": "PASTURE", "build": "BUILD_PASTURE",
              "product": "WOOL", "interval": 3, "max_held": 6},
}
LAND_PRICES = [1000, 2000, 4000]
SEASON_DAYS = 30
MAX_MARKET_ORDERS = 10
SHED_CAPACITY = 100


def _P(name, default):
    """Policy knob, overridable from the environment for sweeps."""
    raw = os.environ.get("KAG_" + name)
    if raw is None:
        return default
    return type(default)(raw)


# Tiles one unit can keep alive in a day, including the walk out from the shed.
# Swept: 8 beats 7 and 9 by ~$1,700. The crew saturates at about eight tiles
# each, and this also sets the hire target, so it is the sharpest knob here.
TILES_PER_UNIT = _P("TILES_PER_UNIT", 8)

# The marginal hand costs ~$6/action around the twelfth hire against ~$11 of
# return, so the curve is still positive here but flattening.
MAX_HANDS = _P("MAX_HANDS", 10)

# Size the crew off the work that actually exists, and off the cash that
# exists to pay for it. Both are new; the old rule counted *tiles owned*.
#
# It counted them badly. The crew is sized from `len(full_plot)`, which is
# every workable tile whether or not anything can be done with it, so the farm
# hires nine hands on day 1 to tend twenty-one planted tiles -- and issue 03
# measured the result: crop hands idle 32.5% of their actions overall and
# **85% on days 1, 3 and 5**.
#
# Worse, hiring never looked at the bank. `MIN_HANDS=8` banks **$0**: the farm
# pays $54/day through the days 0-10 window when it holds ~$300 and has no
# income until the first melon on day 11, goes broke by day 9, and can then
# buy neither seed nor animals ever again -- BUY_SEED is issued twice in a
# whole game and BUY_ANIMAL not at all. Nine hires also crowd the 10-order
# market queue at hours 0-1, which is what truncates the buys.
#
# That last part matters for reading TRIED.md: the recorded "hiring floor of
# 8 / 10 / 12 hands -> 3-21, 3-21, 0-24" was measured on a farm that had gone
# bankrupt, not on a farm with too many hands. It is not evidence about crew
# size, and the conclusions drawn from it -- that extra hands have nothing to
# do, and that hands and land only pay together -- do not follow from it.
HIRE_TO_WORK = _P("HIRE_TO_WORK", 0)
# Keep this much back when sizing the morning's hire, so the crew can never
# eat the seed money. The whole farm turns on planting the premium blocks the
# moment cash allows.
HIRE_CASH_BUFFER = _P("HIRE_CASH_BUFFER", 400)

# Hard ceiling on the morning's hire bill, as a share of the bank. Always on:
# it is what stops the farm hiring itself insolvent. See `_hire_target`.
HIRE_BANK_SHARE = _P("HIRE_BANK_SHARE", 0.25)

# Floor on the daily crew, independent of the tiles-per-unit arithmetic.
# The top public farms run about 12 hands against our derived ~6, and hiring
# is cheap. Swept anyway: 8, 10 and 12 all lose (3-21, 3-21, 0-24), because
# the extra hands have nothing to do on two quadrants. Hands and land only
# pay together, and three quadrants loses on its own here -- see 04-melon.
MIN_HANDS = _P("MIN_HANDS", 0)

# How many quadrants to buy. Land comes straight off the final score, and the
# third quadrant costs $4,000 -- swept at $12,502 for two against $9,405 for
# three, so it never earns that back in the days it has left.
MAX_LAND = _P("MAX_LAND", 2)
LAND_CASH_BUFFER = _P("LAND_CASH_BUFFER", 300)

# Retuned 20 August against **ghosts of our own ladder submissions** rather
# than against `starter`. `make_ghost.py` replays a submission's action tape,
# so the 792- and 804-rated builds -- which exist nowhere but the ladder --
# can be played directly, and the objective becomes games won against them.
#
# The incumbent scored **0 of 18** against those three ghosts on unseen seeds.
# This build scores **10 of 18**, beats the incumbent **21-3** head to head,
# and gives up $6.3k of bank against `starter` doing it. Bank has now picked
# the wrong side seven times in one day; melon 24 banks $76.1k here against
# melon 20's $64.8k and wins 3 of 18 against its 10.
#
# `MELON_LAST_PLANT=9` is the sharpest single move (+2 of 18) and this file
# recorded it as "$8k worse" -- true on bank against an opponent that does not
# contest melon, wrong against one that does. The 804 submission's own note
# reads "melon second cycle cut at day 9 ... 63-1 vs previous build".
# The herd, on the tiles nearest the shed. Sized against what the town drains
# per day, since that is what holds the price up.
N_SHEEP = _P("N_SHEEP", 2)
N_COWS = _P("N_COWS", 13)
N_GEESE = _P("N_GEESE", 0)
GOOSE_TARGET = N_SHEEP + N_COWS + N_GEESE  # total animal tiles
GEESE_PER_RANCHER = _P("GEESE_PER_RANCHER", 5)
# Geese bought before the wheat engine runs simply starve: there is no feed in
# the shed and no cash left to buy any. Hold back enough to keep planting.
GOOSE_CASH_BUFFER = _P("GOOSE_CASH_BUFFER", 700)
GOOSE_START_DAY = _P("GOOSE_START_DAY", 0)

# Hold the land purchases back until the herd is down.
#
# Read off the 804-rated ladder submission, which places cows and sheep on
# **day 0** and buys its second and third quadrants on days 6 and 8. This
# build does the opposite: BUY_LAND is queued ahead of BUY_ANIMAL, so day 0
# spends $1,000 on NE and the rest on melon seed, the farm is broke by day 1,
# and the first cow is not placed until the melon money lands on **day 11**.
#
# A cow first yields eight days after placement, so ours starts milking on day
# 19 against their day 8. The replays show the cost: they sell 273 milk a game
# to our 146. Land cannot earn anything the herd would not have earned sooner.
LAND_START_DAY = _P("LAND_START_DAY", 6)

# Buy the herd before the land, which is the opening the 804-rated submission
# runs. Only useful together with GOOSE_START_DAY=0 and a feed supply -- the
# pieces do not port one at a time.
HERD_FIRST = _P("HERD_FIRST", 1)

# Lay the zones out over the land we plan to own rather than the land we hold
# today, so buying a quadrant does not renumber the crop blocks underneath
# standing plants. Required by any opening that defers land.
PLANNED_ZONES = _P("PLANNED_ZONES", 1)

# Tiles reserved for wheat ahead of melon, nearest the shed. 0 keeps the
# historical zoning, where wheat only ever gets leftovers.
# Six tiles of wheat, taken ahead of melon rather than out of the leftovers.
# Worth 10/18 -> 16/18 against the ghost panel on held-out seeds, and it holds
# the win count while adding $10k of bank on the search seeds. More is worse
# in the way everything is worse here: 10 tiles banks $74.7k and wins 6 of 18,
# 16 tiles banks $76.3k and wins 2.
WHEAT_FIRST_TILES = _P("WHEAT_FIRST_TILES", 20)

# How much of the opponent's visible pipeline to believe when projecting a
# price. 1.0 takes their ground at face value and assumes they sell all of it.
RIVAL_WEIGHT = _P("RIVAL_WEIGHT", 1.0)

# Let a cloned policy choose what each unit does, with the heuristic as the
# fallback for anything it proposes that is not legal.
#
# Only unit control is learned. Hiring, land, animals, seeds and market orders
# stay heuristic: they are a handful of decisions a turn rather than a
# per-cell field, they are already tuned, and keeping them out leaves the
# learned part small enough to fine-tune with self-play later.
#
# The policy is a 48-channel, 3-block residual CNN over the 10x10 board
# producing per-cell action logits; each unit reads the cell it stands on.
# One forward pass a turn serves the whole crew, in numpy, at ~3.2ms against
# a 1000ms actTimeout.
# 0 off. 1 = fill idle only: the policy may act only where the heuristic
# would PASS. 2 = full override, which is what a fine-tuned policy would want.
#
# Mode 1 exists because mode 2 does not survive contact. A clone at 65%
# per-action accuracy still banks **$1**: `PASS` is legal everywhere, so the
# policy's PASS overrides a productive heuristic op, and one mistake moves the
# agent into board states the demonstrations never contained -- the standard
# behavioural-cloning distribution shift, compounded over 720 turns.
#
# Filling idle is the safe half of the same idea. Issue 03 measured 23.8% of
# all unit-actions as PASS, worth nothing by definition, so a wrong guess
# there costs a turn that was already being thrown away.
LEARNED_UNITS = _P("LEARNED_UNITS", 0)
LEARNED_WEIGHTS = os.environ.get("KAG_WEIGHTS", "weights/bc.npz")
# Below this margin over the next-best legal op, defer to the heuristic. The
# clone is only as good as its demonstrators, so it should not overrule a
# tuned rule on a coin-flip.
LEARNED_MARGIN = _P("LEARNED_MARGIN", 0.0)

# DAgger. Cloning from replays alone gives a policy that is 65% accurate on
# expert states and banks $1 when it drives, because the states it reaches
# once it errs are states no demonstration contained. The fix is to train on
# the states the *policy* visits, labelled by an expert -- and here the expert
# is free and exact, because the heuristic can label any board instantly.
#
# `DAGGER_BETA` is the chance of taking the heuristic's op rather than the
# policy's on a given turn. Rolling out at beta=1 collects expert states;
# lowering it walks the data distribution toward the policy's own.
DAGGER_BETA = _P("DAGGER_BETA", 0.0)
# When on, every turn appends (board, unit cells, expert ops) to DAGGER_LOG
# for a harness to drain. Off, it costs one boolean test a turn.
DAGGER_CAPTURE = _P("DAGGER_CAPTURE", 0)
DAGGER_LOG = []

_POLICY = None
_POLICY_TRIED = False
_POLICY_WARNED = False


def _policy():
    """Load the weights once, and never let a missing file break a game."""
    global _POLICY, _POLICY_TRIED
    if _POLICY_TRIED:
        return _POLICY
    _POLICY_TRIED = True
    if LEARNED_UNITS:
        try:
            import nn_features                      # noqa: F401
            from nn_policy import TargetPolicy
            if TargetPolicy.available(LEARNED_WEIGHTS):
                _POLICY = TargetPolicy(LEARNED_WEIGHTS)
        except Exception:
            _POLICY = None                          # heuristic carries on
    return _POLICY

# Choose what to plant, and which animal to buy, from the *projected* price at
# harvest rather than from a fixed zoning fitted once against `starter`.
#
# Both decisions are currently blind in the same way. The melon block is melon
# because a sweep said 20 tiles, whatever the opponent is doing; the herd is
# 6 cows and 2 sheep because a sweep said so, whatever milk and wool are
# worth. But melon is a race into a market that never recovers, so a second
# cycle is worth $250 a unit or $1 depending entirely on whether the other
# farm has melon in the ground -- which is visible.
#
# The forecast is worth trusting here: measured against simply assuming
# today's price holds, it wins on 14 of 15 item/horizon pairs and roughly
# halves the error at long horizons (melon at 16 days, 36.8 against 62.4).
ADAPTIVE_CROP = _P("ADAPTIVE_CROP", 0)
ADAPTIVE_HERD = _P("ADAPTIVE_HERD", 1)
# Only substitute when the alternative is better by this margin, so the farm
# does not thrash between crops on noise.
ADAPTIVE_MARGIN = _P("ADAPTIVE_MARGIN", 1.15)
GOOSE_BUY_RATE = _P("GOOSE_BUY_RATE", 3)
# A goose needs about three days to earn its $300 back, so stop buying once
# the season cannot pay for one.
LAST_GOOSE_DAY = _P("LAST_GOOSE_DAY", 24)

# Wheat held back per goose so feeding never fails. An unfed goose still lays,
# but two consecutive unfed days and it escapes for good.
FEED_RESERVE_PER_GOOSE = _P("FEED_RESERVE_PER_GOOSE", 3)
FEED_CARRY = _P("FEED_CARRY", 6)
# Whether to top the feed reserve up from the market rather than relying on our
# own harvest. Swept at 0: bought wheat costs $25-45 against the ~$20 our own
# sells for, and it competes for the 100-item shed. Growing feed is cheaper
# than buying it, even though a goose returns $140/day either way.
FEED_BUY = _P("FEED_BUY", 0)

# Replant melon ground as strawberry once the melon market is dead.
#
# Traced prices at midday, seed 1000, against `starter`:
#
#   day        0     9    12    18    24    27
#   MELON    256   271   174   184     4    13
#   STRAW    128   169   193   243   285   300
#
# Melon is a race into a market that never recovers -- the town drains 1/day,
# so our own first harvest on day 10-11 crashes it and it stays crashed.
# Strawberry runs the other way: the town drains it 25/day, faster than either
# farm supplies, so it climbs all season and finishes at 2.5x its base price.
#
# The melon block is therefore worth replanting *as melon* only while melon is
# still worth more than the strawberry that could stand there instead. After
# that, a second melon cycle spends ten tile-days to sell into a $4 market and
# knocks down the tail of our own first cycle on the way.
#
# This is not the day-9 and day-13 melon cutoffs already in TRIED.md: those
# stopped planting and left the ground bare. This changes what goes in.
MELON_SWITCH = _P("MELON_SWITCH", 0)
MELON_SWITCH_PRICE = _P("MELON_SWITCH_PRICE", 150)

# Sell timing (issue 10). Everything used to be dumped the turn it reached
# the shed, which is right for some goods and expensive for others.
#
# What this build actually sells is milk, wool, strawberry, melon and
# fertilizer -- it grows no wheat and keeps no geese, so the egg and wheat
# price drift that the docs flag is not ours to exploit. Those five split
# cleanly by whether the town drains them:
#
#   MELON       town drains 1/day  -- never recovers, first seller takes ~$217
#   FERTILIZER  town drains 0/day  -- never recovers, a one-way ~$25k pool
#   MILK        town drains 19/day \
#   WOOL        town drains 13/day  > the price comes back if we let it
#   STRAWBERRY  town drains 25/day /
#
# The first two are races and dumping them is the whole strategy. The last
# three are not: their curves are `linear`/`sq`, so they are at the $1 floor
# by unit 50-60, and a harvest wave sold in one order eats that crash in a
# single turn. Selling them a slice at a time spreads the same stock across
# the 24 turns of a day, and the town drains between slices.
#
# Strawberry is the binding case: 44 tiles yield four times each, so a yield
# day lands ~44 units against a drain of 25/day. At one a turn we clear 24 a
# day, which is about the drain rate -- hence the default.
SELL_METER = _P("SELL_METER", 0)
SELL_CHUNK = _P("SELL_CHUNK", 1)
METERED = ("STRAWBERRY", "MILK", "WOOL")

# Stop metering and clear the shelves this late: unsold stock scores zero.
METER_LAST_DAY = _P("METER_LAST_DAY", SEASON_DAYS - 3)

# Stop metering when the shed gets this full. Overflow past the 100-item cap
# is destroyed at end of day, and the feed reserve already holds a third of
# it, so a slow drip is not worth losing the stock it is protecting.
METER_SHED_LIMIT = _P("METER_SHED_LIMIT", 70)

# Carry this much before making a shed trip. Harvests arrive in waves, and a
# wave larger than the 100-item shed cap is silently discarded at end of day.
DROP_THRESHOLD = _P("DROP_THRESHOLD", 14)

# From this hour on the last day, units stop tending and start converting:
# harvest what is ripe and carry it to the shed. Unsold inventory scores zero,
# and the end-of-day drop happens after the reward is taken, so anything still
# in a unit's hands at the buzzer is thrown away.
FLUSH_HOUR = _P("FLUSH_HOUR", 15)

# Every day, not just the last: from this hour a loaded unit delivers, so the
# produce can be sold in the turns that remain. The end-of-day drop discards
# anything past the 100-item shed cap, and the feed reserve already occupies a
# third of it, so a crew carrying 80 units into the night loses some. 24
# disables it.
DAILY_FLUSH_HOUR = _P("DAILY_FLUSH_HOUR", 24)

# Front-run the opponent's premium dump. Both farms are public, so a melon
# crop ripening on their side is visible before it reaches the market. Melon
# is drained by the town at only 1/day and its price curve is quadratic in
# the glut, so it never recovers: whoever sells first takes ~$217 a unit and
# the other gets the floor. When their melons are ready, ours stop waiting
# for a full load and go to the shed now, where SELL can actually see them.
# Swept off: it loses 2-22 head to head even when gated to units carrying
# melon. Breaking off to deliver costs more action economy than beating the
# opponent to the melon price is worth.
FRONT_RUN = _P("FRONT_RUN", 0)

# Weight on distance when breaking ties within an urgency tier. 0 makes a
# unit work its block in a fixed order regardless of where it is standing.
TIEBREAK_DIST = _P("TIEBREAK_DIST", 1)

# How many steps of walking one tier of urgency is worth.
#
# Task choice used to be strictly lexicographic: the most urgent tile in the
# block won no matter how far away it was, and distance only broke ties inside
# a tier. That is why a unit would walk seven tiles past a ripe melon to water
# something, then walk back. Scoring `tier * URGENCY_W + dist` instead lets a
# near task outrank a slightly more urgent far one.
#
# The board is 10x10, so the largest possible distance is 18, and any value
# above that reproduces the old lexicographic order exactly. Swept 0..1000:
# everything from 5 up is byte-identical to lexicographic, and the curve
# rises all the way down to 0. At 0 a unit simply does the nearest actionable
# task and urgency only breaks ties between equidistant ones -- which beat
# the previous build 24-0 head to head, both seats.
URGENCY_W = _P("URGENCY_W", 0)

# Rank tasks by dollars per action instead of by distance alone.
#
# `URGENCY_W=0` was a large win, but it left task choice *value-blind*: it
# minimises walking distance and uses the urgency tier only to break exact
# ties. So any cheap task standing near an expensive one steals the action --
# which is why bridge wheat banked +$6,214 against `starter` and still lost
# 0-24 in the mirror. A tour over mispriced tasks optimises the wrong thing.
#
# With this on, a task is scored `value / (dist + 1)`: the dollars it earns
# against the actions it costs, the walk included, since reaching a tile `d`
# steps away and acting costs `d + 1` actions. It degrades to the current
# behaviour when every reachable task is worth the same, and to the old
# lexicographic order when the values are far apart.
PRICED_ROUTING = _P("PRICED_ROUTING", 0)

# The tier at and below which pricing is *not* applied, so the old absolute
# ordering still holds. Pricing every task was tried first and lost 4-20: a
# rescue is worth what the tile still owes for the season, not what tonight's
# unit sells for, so a dying wheat plant priced at 4 x $21 loses to a melon
# watering at $217 -- and then the plant is a weed by morning and the tile is
# gone. Losses here are unrecoverable and asymmetric, so they are not traded.
# 0 = T_RESCUE only; 1 also protects T_SETUP; -1 prices everything.
PRICED_URGENT_TIER = _P("PRICED_URGENT_TIER", 0)

# What one unit of each product is worth, used only to price tasks above.
# These are the environment's base prices -- the same numbers the tier
# ordering below was already reasoning with -- deliberately static rather than
# read from `obs["market"]`. A live price makes routing chase the market down
# as it crashes; ranking tasks and timing sales are separate problems (see
# issue 10). Exposed as knobs so `sweep.py` can move them.
UNIT_VALUE = {
    "MELON": _P("V_MELON", 217),
    "STRAWBERRY": _P("V_STRAWBERRY", 120),
    "WHEAT": _P("V_WHEAT", 21),
    "MILK": _P("V_MILK", 160),
    "WOOL": _P("V_WOOL", 200),
    "EGG": _P("V_EGG", 50),
    "FERTILIZER": _P("V_FERTILIZER", 80),
}

# How to order tiles before splitting them into per-unit blocks.
#   0 = by distance from the shed. Tiles at equal distance lie on a diagonal,
#       so a "contiguous" chunk is an arc spanning the whole quadrant.
#   1 = serpentine rows, which keeps consecutive tiles genuinely adjacent.
BLOCK_ORDER = _P("BLOCK_ORDER", 1)

# Tiles given over to melon, taken just outside the animal zone. The market
# pays $21,721 for the first 100 melons and almost nothing past 150, and the
# town drains only one a day, so this is a race against the opponent rather
# than a production problem: plant early, sell on harvest. Swept at 24, and
# bracketed: 16 loses to it 3-21, and 30, 36 and 44 all lose to it 0-24.
# The old value of 16 was fitted when the spare land grew wheat.
MELON_TILES = _P("MELON_TILES", 18)
MELON_LAST_PLANT = _P("MELON_LAST_PLANT", 9)

# Tiles given to strawberry, just outside the melon block. Ongoing crop: it
# yields four times off one planting, so it costs one plant action and then
# only survival watering. Worth ~$34/action against wheat's ~$14, and the
# town drains 25/day so the price holds.
# Takes every tile the herd and the melon block do not, so the farm grows no
# wheat at all -- feed is bought. That is the point: a wheat tile earns ~$16
# a day against strawberry's ~$28, and buying feed had already made wheat
# nearly redundant without anything being re-derived to replace it.
#
# This was rejected once, at 8 and 14 tiles, both of which lose. The curve is
# not monotonic: 16 wins, and it keeps improving to the point where
# strawberry covers everything left. Two samples on the wrong side of a
# threshold looked like a dead idea.
# Cut from 44 to 34 on 20 August, on replay evidence rather than a sweep. Ten
# tiles come off strawberry and fall back to wheat (`crop_of` defaults to it),
# which is worth 21-3 head to head and +$3,422 vs `starter`.
#
# Ten real losses say the farms that beat us sell **184 wheat a game to our
# 44**, while we out-produce them on milk and fertilizer. Wheat is the largest
# town drain in the game at 31/day, its curve is `log` so it never crashes,
# and its price climbs $26 -> $51 across the season. We had priced it at its
# $25 base and concluded it was redundant once feed was bought.
#
# This is not bridge wheat, which lost 0-24. That put wheat on melon and
# strawberry ground and desynchronised the premium blocks; this gives wheat
# ground of its own and never touches the premium blocks' timing.
STRAWBERRY_TILES = _P("STRAWBERRY_TILES", 43)

# Never leave ground bare. An action tally on 20 August found crop hands idle
# 32.5% of their actions, and tracing why showed it is not a scheduling
# problem: there is nothing on the tiles. Two windows, for two reasons.
#
#   Days 1-10   the bank sits at $300 falling to $120 -- everything went on
#               animals and melon seed on day 0 -- so LAND_CASH_BUFFER blocks
#               every further seed purchase and 15 tiles stay bare until the
#               first melon lands on day 11.
#   Days 20-28  melon and strawberry both stop being plantable on day 19, so
#               29 tiles sit bare for the last eight days with $40k+ in the
#               bank and a full crew with nothing to do.
#
# Wheat is the filler for both: $10 a seed, a four-day cycle, and a `log`
# market that holds ~$20 at any volume we can reach (and drifts up to ~$47 by
# day 28, since the town drains 31/day). It loses to strawberry on a tile
# either of them could have -- which is why the farm grows none in steady
# state -- but the comparison here is against bare dirt earning nothing.
# Both default OFF. Bridging both windows banks +$2,567 against `starter` and
# then loses to the build without it **0-24 head to head**, which is the exact
# failure mode TRIED.md warns about: bank vs `starter` is a filter, not the
# objective. The mechanism is `URGENCY_W=0` -- a unit takes the nearest
# actionable task and is blind to what it is worth, so cheap wheat work planted
# next to a melon steals the watering that melon needed. Melon's window is
# worth ~$217 a watering and wheat's is worth ~$5. Filling idle tiles only pays
# once task choice knows the difference; see docs/issues/03.
BRIDGE_EARLY = _P("BRIDGE_EARLY", 0)   # days 1-10, tiles we cannot afford seed for
BRIDGE_LATE = _P("BRIDGE_LATE", 0)     # days 20+, tiles past their crop's cutoff
# Whether the bridge may take melon-zoned ground. It must not. Melon is a race
# into a market the town drains at 1/day, so it never recovers and the first
# seller takes ~$217 a unit. Holding melon tiles under a wheat cycle means
# melon goes in whenever a tile happens to come free, and the block that used
# to sit flat at 24 and harvest in one lump wanders all season -- day 11 banked
# $4.7k instead of $8.6k. Our own later melons then sell into the market our
# own earlier melons crashed.
BRIDGE_MELON = _P("BRIDGE_MELON", 0)
# Bridge wheat is bought after every other order, so it spends what is left.
# LAND_CASH_BUFFER is what strands the early season; wheat at $10 a seed does
# not need that much protection, only enough to cover tomorrow's hire bill.
BRIDGE_CASH_BUFFER = _P("BRIDGE_CASH_BUFFER", 100)

# Wheat planted later than this cannot reach max_yield_day before the season
# ends, so the tile is better left empty.
def _last_plant_day(crop):
    """Latest day a crop can be planted and still reach harvest.

    Melon also takes a policy cap: a second cycle harvests into a market its
    own first cycle already knocked down, so late plantings can be worth less
    than the wheat or geese the tile would otherwise carry.
    """
    latest = SEASON_DAYS - 1 - CROP_SPEC[crop]["harvest_age"]
    if crop == "MELON":
        return min(latest, MELON_LAST_PLANT)
    return latest


LAST_PLANT_DAY = _last_plant_day("WHEAT")

# Whether to CARE for geese. One action banks +1 on the next production, so it
# is worth ~$40/action -- real, but it competes with harvesting at $160.
CARE_ENABLED = _P("CARE_ENABLED", 1)

# Tier ordering for tasks, lower being more urgent. These are ordered by
# dollars per action, which is the only currency that matters here:
#
#   harvest a full goose  4 eggs           ~$160   <- was ranked below fertilizer
#   collect fertilizer    1 unit           ~$80
#   feed                  enables 2 eggs   ~$80/day
#   care                  +1 egg            ~$40
#
# Fertilizer used to outrank harvesting, so a rancher emptied every fertilizer
# tile in its block before touching a single goose. Five of sixteen birds then
# sat at max_held from day 20 to the end of the season, destroying every egg
# they produced -- about $4,500 a game.
T_RESCUE = 0        # dies or escapes tonight if untouched
T_SETUP = 1         # a goose not yet earning is the most expensive idle asset
T_HARVEST_FULL = 2  # at max_held: tonight's production is being thrown away
T_FERT = 3
T_FEED = 4
T_HARVEST = 5
T_CARE = 6
T_WATER = 7         # yield bonus only; the plant is in no danger
T_PLANT = 8
T_DIG = 9


def _crop_value(crop):
    """Sale value of one harvested unit of `crop`."""
    return UNIT_VALUE.get(crop, UNIT_VALUE["WHEAT"])


def _plant_value(crop):
    """Dollars per action of planting `crop`, amortised over its whole cycle.

    A plant action earns nothing by itself; what it buys is the cycle. Pricing
    it at the cycle rate stops planting from either dominating a ripe harvest
    or being ignored next to a watering.
    """
    spec = CROP_SPEC.get(crop)
    if spec is None:
        return 0.0
    return spec["units"] * _crop_value(crop) / float(spec["actions"])


def _animal_day_value(want):
    """What one animal earns in a day, at base price.

    CARE banks +1 a day and pays out on the next scheduled production, so an
    animal on interval `i` yields `1 + i` units every `i` days.
    """
    spec = ANIMAL_SPEC[want]
    interval = spec["interval"]
    per_day = (1.0 + interval) / interval
    return per_day * UNIT_VALUE.get(spec["product"], 0)


# ---------------------------------------------------------------- market model
#
# A copy of the environment's pricing, so the agent can price a *future*
# harvest rather than only react to today's board. A submitted agent cannot
# import kaggle_environments, so these are duplicated rather than referenced.
#
# The point of having it here is that every input to a future price is
# observable: current inventory and the unlocked shops are in the observation,
# and **both farms' tiles are public**, so the supply already in the ground on
# either side can be counted. That makes the price a crop will fetch when it
# ripens a computable quantity instead of a guess.
#
# The shape of the curves is what makes it worth doing. Premium goods are
# violently steep and staples are flat: milk, strawberry and melon reach the
# $1 floor about 200 units above I0, while wheat (T=400, `log` above) and egg
# (T=332, `log`) barely move at any volume two farms can reach. Being wrong
# about melon is expensive; being wrong about wheat is not.
MARKET_I0 = 10000
PRICE_FLOOR = 1
HINGE_GAIN = 8.0
# base, T, below_func, below_target, above_func, above_target
MARKET_PARAMS = {
    "WHEAT":      (25, 400, "sqrt", 0.8, "log", 0.2),
    "CARROT":     (35, 450, "hinge", 1.0, "sqrt", 0.7),
    "TOMATO":     (60, 200, "hinge", 0.4, "sqrt", 0.6),
    "STRAWBERRY": (120, 100, "sqrt", 0.7, "linear", 1.6),
    "MELON":      (250, 300, "log", 0.2, "sq", 3.6),
    "EGG":        (50, 332, "hinge", 0.4, "log", 0.2),
    "MILK":       (160, 122, "sqrt", 0.6, "linear", 1.6),
    "WOOL":       (200, 105, "log", 0.2, "sq", 3.2),
    "FERTILIZER": (100, 200, "linear", 0.4, "linear", 0.4),
}
SHOP_WANTS = {
    "BAKERY": ("EGG", "WHEAT"),
    "PIZZA_SHOP": ("MILK", "TOMATO", "WHEAT"),
    "BRUNCH_SPOT": ("EGG", "WHEAT", "STRAWBERRY"),
    "YARN_STORE": ("WOOL",),
    "ICE_CREAM_SHOP": ("STRAWBERRY", "MILK", "WHEAT"),
    "PET_CAFE": ("CARROT",),
    "SMOOTHIE_SHOP": ("STRAWBERRY", "MILK"),
    "FARMERS_MARKET": ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY"),
}
TOWN_CENTER_PRODUCTS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
                        "EGG", "MILK", "WOOL")


def _shape(func, x, T):
    if func == "linear":
        return x
    if func == "sq":
        return x * x
    if func == "sqrt":
        return x ** 0.5
    if func == "log":
        return math.log(1.0 + x)
    if func == "hinge":
        if not T or T <= 0:
            return x
        u = x / float(T)
        return u + HINGE_GAIN * max(0.0, u - 1.0) ** 2
    return x


def _price_at(item, inventory):
    """What one unit fetches at a given market inventory."""
    spec = MARKET_PARAMS.get(item)
    if spec is None:
        return 0.0
    base, T, below_f, below_t, above_f, above_t = spec
    if inventory < MARKET_I0:
        amp = below_t * base / _shape(below_f, T, T)
        price = base + amp * _shape(below_f, MARKET_I0 - inventory, T)
    else:
        amp = above_t * base / _shape(above_f, T, T)
        price = base - amp * _shape(above_f, inventory - MARKET_I0, T)
    return max(PRICE_FLOOR, price)


def _drain_rates(town):
    """Units a day the town removes, per product -- exactly, not on average.

    The town centre takes one of each non-fertilizer product a day. Each
    unlocked shop *instance* consumes one of everything it demands every four
    turns, doubled when it wants only one product. `unlocked_shops` lists
    instances and repeats them, so this is the real rate for this game rather
    than an expectation over the random draw.
    """
    rate = {}
    for p in MARKET_PARAMS:
        rate[p] = 1.0 if p in TOWN_CENTER_PRODUCTS else 0.0
    for name in (town or {}).get("unlocked_shops", []) or []:
        wants = SHOP_WANTS.get(name)
        if not wants:
            continue
        per_day = 12.0 if len(wants) == 1 else 6.0
        for p in wants:
            rate[p] = rate.get(p, 0.0) + per_day
    return rate


def _pipeline(farm, day, horizon):
    """Units each product will bring to market inside `horizon` days.

    Both farms are counted the same way, which is the whole point: the
    opponent's tiles are public, so melon ripening on their side is visible
    days before it lands and craters the price we were counting on.
    """
    out = {}
    for row in (farm.get("tiles") or []):
        for t in row:
            if not isinstance(t, dict):
                continue
            if t.get("kind") == "PLANT":
                crop = t.get("crop")
                spec = CROP_SPEC.get(crop)
                if spec is None:
                    continue
                age = day - t.get("planted_day", day)
                if spec.get("ongoing"):
                    left = max(0, spec["harvest_age"] + 6 - age)
                    n = min(horizon, left) / 2.0
                else:
                    due = spec["harvest_age"] - age
                    n = spec["units"] if 0 <= due <= horizon else 0
                if n:
                    out[crop] = out.get(crop, 0.0) + n
            elif t.get("animal"):
                spec = ANIMAL_SPEC.get(t["animal"])
                if not spec:
                    continue
                interval = max(1, spec["interval"])
                out[spec["product"]] = out.get(spec["product"], 0.0) + \
                    horizon * (1.0 + interval) / interval
                out["FERTILIZER"] = out.get("FERTILIZER", 0.0) + horizon
    return out


def _market_view(obs, player):
    """Everything needed to price a harvest `d` days from now."""
    farms = obs.get("farms") or []
    day = obs["day"]
    mine = _pipeline(farms[player], day, 30) if len(farms) > player else {}
    theirs = _pipeline(farms[1 - player], day, 30) if len(farms) > 1 else {}
    return {"inv": dict((obs.get("market") or {}).get("inventory") or {}),
            "drain": _drain_rates(obs.get("town")),
            "mine": mine, "theirs": theirs, "day": day}


def _projected_price(view, item, days):
    """Price `item` fetches when something planted now ripens in `days`.

    Inventory moves three ways in between: the town drains it, we add to it,
    and so does the opponent. Their share is scaled by RIVAL_WEIGHT, since
    counting their ground assumes they sell all of it.
    """
    if days <= 0:
        days = 1
    inv = view["inv"].get(item, MARKET_I0)
    frac = min(1.0, days / 30.0)
    inv -= view["drain"].get(item, 0.0) * days
    inv += view["mine"].get(item, 0.0) * frac
    inv += view["theirs"].get(item, 0.0) * frac * RIVAL_WEIGHT
    return _price_at(item, inv)


def _crop_rate(view, crop):
    """Dollars per tile-day for planting `crop` now, at projected prices.

    A tile is an asset let for the crop's whole occupancy, so the comparison
    has to be per tile-day: melon returns six units in eleven days, strawberry
    four over seventeen. Each is valued at what it will fetch when it lands,
    not at what it would fetch today.
    """
    spec = CROP_SPEC.get(crop)
    if spec is None:
        return 0.0
    if spec.get("ongoing"):
        life = spec["harvest_age"] + 6
        horizon = spec["harvest_age"] + 3      # middle of its yield run
    else:
        life = spec["harvest_age"] + 1
        horizon = spec["harvest_age"]
    price = _projected_price(view, crop, horizon)
    return spec["units"] * price / float(life)


def _animal_rate(view, kind):
    """Dollars per tile-day for placing `kind` now, at projected prices.

    CARE banks +1 a day and pays out on the next scheduled production, so an
    animal on interval `i` yields `1 + i` units every `i` days. Fertilizer is
    a second stream off the same tile and is counted, since it is what makes a
    neglected animal still worth its ground.
    """
    spec = ANIMAL_SPEC.get(kind)
    if spec is None:
        return 0.0
    interval = max(1, spec["interval"])
    per_day = (1.0 + interval) / interval
    horizon = spec.get("first_yield", 8)
    return (per_day * _projected_price(view, spec["product"], horizon)
            + _projected_price(view, "FERTILIZER", horizon))


def _legal_op(op, tile, day, carrying, at_shed, seeds, crop, want_animal,
              has_animal):
    """Can this unit actually do `op` where it stands?

    The policy is free to propose anything; the environment silently drops an
    illegal action, and a silently dropped action is a wasted unit-turn. So
    every proposal is checked against the tile before it is used, and anything
    that fails falls through to the next-best or to the heuristic.
    """
    if op in ("NORTH", "SOUTH", "EAST", "WEST", "PASS"):
        return True
    is_plant = isinstance(tile, dict) and tile.get("kind") == "PLANT"
    is_weed = isinstance(tile, dict) and tile.get("kind") == "WEED"
    animal = isinstance(tile, dict) and tile.get("animal")
    struct = isinstance(tile, dict) and tile.get("kind") in ("COOP", "PASTURE")

    if op == "WATER":
        return is_plant and not tile.get("watered_today")
    if op == "HARVEST":
        return (is_plant or animal) and tile.get("yield_units", 0) > 0
    if op == "PLANT":
        return tile is None and seeds.get(crop, 0) > 0
    if op == "DIG":
        return is_weed or (struct and not animal)
    if op == "FERTILIZE":
        return is_plant
    if op in ("FEED", "CARE"):
        return bool(animal)
    if op == "COLLECT_FERTILIZER":
        return bool(animal) and bool(tile.get("fertilizer_available"))
    if op == "DROP":
        return at_shed and carrying > 0
    if op == "PICKUP":
        return at_shed
    if op == "PLACE":
        return struct and not animal and has_animal
    if op == "BUILD_COOP":
        return tile is None and want_animal == "GOOSE"
    if op == "BUILD_PASTURE":
        return tile is None and want_animal in ("COW", "SHEEP")
    return False


def _step_toward(x, y, tx, ty):
    if x < tx:
        return "EAST"
    if x > tx:
        return "WEST"
    if y < ty:
        return "SOUTH"
    if y > ty:
        return "NORTH"
    return "PASS"


def _quadrant_rank(x, y):
    return (0 if y < 5 else 2) + (0 if x < 5 else 1)


def _shed_dist(x, y):
    return abs(x - 4.5) + abs(y - 4.5)


def _nearest_shed_tile(x, y):
    return min(SHED_ACCESS, key=lambda t: abs(t[0] - x) + abs(t[1] - y))


def _workable_tiles(tiles):
    """Unlocked tiles we are willing to use, nearest the shed first.

    The four shed-access tiles stay clear: they are the only squares from which
    PICKUP and DROP work, and feed comes through them every day.
    """
    out = []
    for y, row in enumerate(tiles):
        for x, tile in enumerate(row):
            if tile == "LOCKED" or (x, y) in SHED_ACCESS:
                continue
            out.append((_shed_dist(x, y), x, y))
    out.sort()
    return [(x, y) for _, x, y in out]


# Quadrants in the order the environment sells them. NW is free.
LAND_BUY_ORDER = ("NE", "SW", "SE")


def _quad_name(x, y):
    return ("NW" if x < 5 else "NE") if y < 5 else ("SW" if x < 5 else "SE")


def _planned_tiles(tiles, max_land):
    """Every tile we *intend* to own, nearest the shed first.

    Zoning has to be stable from turn 0, and building it from currently
    unlocked tiles is not: `melon_zone = full_plot[m0:m0+MELON_TILES]` names
    different physical squares the moment a quadrant is bought. That is
    harmless when land is bought on day 0, because the board settles before
    anything is planted -- and ruinous for a herd-first opening that defers
    land to day 6, because zones then shift under standing crops and a tile
    watered as wheat becomes melon ground mid-cycle.

    Locked tiles are included so the plan does not move; they simply carry no
    task until the quadrant is bought, since a "LOCKED" tile is not a dict and
    every classifier returns None for it.
    """
    want = {"NW"}
    for q in LAND_BUY_ORDER[:max(0, max_land)]:
        want.add(q)
    out = []
    for y, row in enumerate(tiles):
        for x, _t in enumerate(row):
            if (x, y) in SHED_ACCESS or _quad_name(x, y) not in want:
                continue
            out.append((_shed_dist(x, y), x, y))
    out.sort()
    return [(x, y) for _, x, y in out]


def _block_key(t):
    """Sort key that keeps a unit's block spatially compact.

    Ordering by distance from the shed looks tidy and is wrong: every tile at
    the same distance sits on a diagonal, so a contiguous slice of that order
    is an arc stretched across the quadrant and the unit walks it end to end.
    Serpentine rows keep consecutive tiles next to each other.
    """
    x, y = t
    if not BLOCK_ORDER:
        return (_quadrant_rank(x, y), _shed_dist(x, y), x, y)
    return (_quadrant_rank(x, y), y, x if y % 2 == 0 else -x)


def _territories(plot, n_units):
    """Split a plot into `n_units` contiguous, spatially local blocks.

    Sorting by quadrant before distance keeps each block in one corner of the
    board, so a unit walks between neighbouring tiles instead of across the
    farm. Interleaving instead (`plot[i::n]`) scatters each unit's tiles over
    the whole board and burns the day on movement.
    """
    blocks = [[] for _ in range(max(1, n_units))]
    if not plot:
        return blocks
    ordered = sorted(plot, key=_block_key)
    per = max(1, (len(ordered) + len(blocks) - 1) // len(blocks))
    for i, tile in enumerate(ordered):
        blocks[min(len(blocks) - 1, i // per)].append(tile)
    return blocks


def _needs_water(tile, day):
    """Water only when it buys something: survival, or yield.

    A plant dies after two consecutive dry days, so one dry day is free. Inside
    the bonus window each watering is worth a unit of yield, so water there
    regardless. Outside it, water only to keep the plant alive -- which for
    melon means alternate days for its first six, then daily through the window.
    """
    if tile.get("watered_today"):
        return False
    if tile.get("consecutive_unwatered", 0) >= 1:
        return True  # dry again tonight and it is a weed by morning
    spec = CROP_SPEC.get(tile.get("crop"))
    if spec is None:
        return False
    start, end = spec["window"]
    return start <= day - tile.get("planted_day", day) <= end


def _crop_task(tile, day, crop="WHEAT"):
    """What a crop tile needs, or None. `crop` is what this tile is zoned for.

    Returns `(tier, op, value)`, where value is the dollars the action earns.
    Only PRICED_ROUTING reads the value; the tier is what orders tasks today.
    """
    last_day = day >= SEASON_DAYS - 1
    if tile is None:
        if last_day or day > _last_plant_day(crop):
            return None
        return (T_PLANT, "PLANT", _plant_value(crop))
    if not isinstance(tile, dict):
        return None
    kind = tile.get("kind")
    if kind == "PLANT":
        age = day - tile.get("planted_day", day)
        grown = tile.get("crop", crop)
        spec = CROP_SPEC.get(grown, CROP_SPEC["WHEAT"])
        ripe = spec["harvest_age"]
        held = tile.get("yield_units", 0)
        unit = _crop_value(grown)
        if held > 0 and (age >= ripe or last_day):
            # Harvest banks the whole stack for one action.
            return (T_HARVEST, "HARVEST", held * unit)
        # On the last day a plant that cannot be harvested is worth nothing,
        # and watering it is an action not spent converting stock to cash.
        if last_day:
            return None
        if _needs_water(tile, day):
            # A plant one dry day from death outranks everything else; a plant
            # merely missing yield does not.
            dying = tile.get("consecutive_unwatered", 0) >= 1
            if dying:
                # Letting it die forfeits the whole tile, not just tonight's
                # unit, so a rescue is priced at the finished crop.
                return (T_RESCUE, "WATER", spec["units"] * unit)
            # Inside the bonus window each watering is worth exactly one more
            # unit of yield.
            return (T_WATER, "WATER", unit)
        return None
    if kind == "WEED":
        if last_day:
            return None
        # Digging earns nothing itself; it buys back a tile that can be
        # planted. Past the crop's cutoff nothing can be planted on it again,
        # so clearing it buys nothing and must not outbid a harvest.
        spent = day > _last_plant_day(crop)
        return (T_DIG, "DIG", 0.0 if spent else _plant_value(crop))
    return None


def _animal_task(tile, day, has_wheat, has_animal, build_budget, want):
    """What a tile in the animal zone needs, or None.

    `want` is the animal this tile is zoned for, and `has_animal` whether the
    unit is carrying one of that kind.
    """
    spec = ANIMAL_SPEC[want]
    if tile is None:
        # An empty structure is a dead tile, so only build when an animal is
        # actually waiting for one. Building twelve on day 1 cost us an opening.
        if day <= LAST_GOOSE_DAY and build_budget > 0:
            return (T_SETUP, spec["build"], _animal_day_value(want))
        return _crop_task(tile, day)
    if not isinstance(tile, dict):
        return None
    if "animal" not in tile:
        if day >= SEASON_DAYS - 1:
            return None  # placing an animal now earns nothing
        if tile.get("kind") == spec["structure"]:
            if has_animal:
                return (T_SETUP, "PLACE", _animal_day_value(want))
            return None
        # A crop or a weed squatting on the animal zone; treat it normally.
        return _crop_task(tile, day)

    last_day = day >= SEASON_DAYS - 1
    living = tile["animal"]
    held = tile.get("yield_units", 0)
    max_held = ANIMAL_SPEC[living]["max_held"]
    unit = UNIT_VALUE.get(ANIMAL_SPEC[living]["product"], 0)
    day_value = _animal_day_value(living)

    # Escaping costs the whole animal -- $400 for a cow, $500 for a sheep -- so
    # feeding a hungry one beats everything. It still produces while unfed; it
    # does not survive two days.
    if tile.get("consecutive_unfed", 0) >= 1 and not tile.get("fed_today") and has_wheat:
        return (T_RESCUE, "FEED", ANIMAL_SPEC[living]["cost"])
    # At max_held, tonight's production is thrown away. Harvest also returns the
    # whole stack for one action, which makes it the best action available.
    if held >= max_held or (last_day and held > 0):
        # The stack, plus the production that is otherwise thrown away tonight.
        extra = 0 if last_day else day_value
        return (T_HARVEST_FULL, "HARVEST", held * unit + extra)
    # One action for ~$80, available daily whether or not the animal was fed.
    if tile.get("fertilizer_available"):
        return (T_FERT, "COLLECT_FERTILIZER", UNIT_VALUE["FERTILIZER"])
    if not tile.get("fed_today") and has_wheat and not last_day:
        return (T_FEED, "FEED", day_value)
    if held >= max_held - 1:
        return (T_HARVEST, "HARVEST", held * unit)
    # CARE banks +1 for the next production, but only pays out on a fed day.
    if (CARE_ENABLED and tile.get("fed_today")
            and not tile.get("cared_today") and not last_day):
        return (T_CARE, "CARE", unit)
    if held > 0:
        return (T_HARVEST, "HARVEST", held * unit)
    return None



def _task_key(tier, value, dist):
    """Sort key for one candidate task, smaller being better.

    Without PRICED_ROUTING this is the historical `tier * URGENCY_W + dist`,
    which at `URGENCY_W=0` is pure distance with the tier as a tiebreak.

    With it, tasks are ranked on dollars per action. Reaching a tile `dist`
    steps away and acting on it costs `dist + 1` actions, so the rate is
    `value / (dist + 1)`; it is negated because the key is minimised. Tier and
    distance stay on as tiebreaks, which is what decides between two tasks of
    equal worth.
    """
    if PRICED_ROUTING:
        # Existential work is not for sale: a plant that dies or an animal that
        # escapes costs the whole tile for the rest of the season, which no
        # single rich action pays back. Those tiers keep the absolute ordering
        # and everything else competes on rate.
        if tier <= PRICED_URGENT_TIER:
            return (0, tier, dist, 0.0)
        return (1, 0, 0, -(value / (dist + 1.0)))
    return (tier * URGENCY_W + dist, tier, dist, 0.0)


def _best_task(tiles, block, classify, pos):
    """Most urgent task in the block, nearest first within a tier.

    The distance term is not a nicety: without it a unit targets whichever
    equally-urgent tile happens to come first in block order, and re-targets
    every time some other tile completes. That churn put 72% of all
    unit-actions into movement.
    """
    best = None
    for (tx, ty) in block:
        got = classify(tiles[ty][tx])
        if got is None:
            continue
        tier, op, value = got
        dist = TIEBREAK_DIST * (abs(tx - pos[0]) + abs(ty - pos[1]))
        key = _task_key(tier, value, dist)
        if best is None or key < best[0]:
            best = (key, (tx, ty), op, tier)
    if best is None:
        return None
    return (best[3], best[1], best[2])


# Where the router last sent each unit. The learned policy is trained to
# predict this rather than the raw op: a target is what the heuristic actually
# chooses, and a 10x10 spatial softmax can express it, where a per-cell op
# head cannot express "walk five tiles to that melon".
_LAST_TARGET = []


def _best_task_at(block, classify_at, pos, scorer=None):
    """As `_best_task`, but the classifier sees the position so it can look up
    which crop that tile is zoned for.

    With a `scorer`, the choice among *actionable* tiles is handed to it --
    which is how the learned policy plugs in. It can only ever pick a tile
    that already has work on it, so the failure mode that sank the op-head
    policy (wandering to cells with nothing to do) is not reachable: the
    learned part chooses which job, the heuristic still decides what the job
    is and how to execute it.
    """
    best = None
    for (tx, ty) in block:
        got = classify_at((tx, ty))
        if got is None:
            continue
        tier, op, value = got
        if scorer is not None:
            key = (-scorer(tx, ty),)
        else:
            dist = TIEBREAK_DIST * (abs(tx - pos[0]) + abs(ty - pos[1]))
            key = _task_key(tier, value, dist)
        if best is None or key < best[0]:
            best = (key, (tx, ty), op, tier)
    if best is None:
        return None
    return (best[3], best[1], best[2])


def _go(pos, target, op_here):
    # Every unit op funnels through here, so this is the one place that sees
    # both where a unit is and where it was sent.
    _LAST_TARGET.append(tuple(target))
    if tuple(pos) == tuple(target):
        return op_here
    return [_step_toward(pos[0], pos[1], target[0], target[1])]


def _rancher_op(tiles, pos, block, day, hour, inv, carried, shed,
                wheat_in_shed, animal_of, rush=False, scorer=None):
    """One op for a unit working the animal zone."""
    has_wheat = inv.get("WHEAT", 0) > 0

    flush = (hour >= FLUSH_HOUR if day >= SEASON_DAYS - 1 else hour >= DAILY_FLUSH_HOUR)
    if (flush or (rush and carried > 0)) and carried > 0:
        return _go(pos, _nearest_shed_tile(*pos), ["DROP"])

    animals = [(x, y) for (x, y) in block
               if isinstance(tiles[y][x], dict) and "animal" in tiles[y][x]]
    empty_structs = [(x, y) for (x, y) in block
                     if isinstance(tiles[y][x], dict)
                     and tiles[y][x].get("kind") in ("COOP", "PASTURE")
                     and "animal" not in tiles[y][x]]
    unfed = [(x, y) for (x, y) in animals if not tiles[y][x].get("fed_today")]
    starving = [(x, y) for (x, y) in unfed
                if tiles[y][x].get("consecutive_unfed", 0) >= 1]

    # An animal that misses a second day is gone along with its price, so
    # fetching feed for it outranks anything else -- including building the
    # structures that were previously starving the herd.
    if starving and not has_wheat and wheat_in_shed > 0 and day < SEASON_DAYS - 1:
        return _go(pos, _nearest_shed_tile(*pos),
                   ["PICKUP", "WHEAT", min(FEED_CARRY, wheat_in_shed)])

    def classify_at(xy):
        want = animal_of(xy)
        spec = ANIMAL_SPEC[want]
        # Animals of this kind on hand, less the structures already waiting for
        # one, so we never build ahead of stock.
        waiting = shed.get(want, 0) + inv.get(want, 0)
        pending = sum(1 for c in empty_structs
                      if tiles[c[1]][c[0]].get("kind") == spec["structure"]
                      and animal_of(c) == want)
        return _animal_task(tiles[xy[1]][xy[0]], day, has_wheat,
                            inv.get(want, 0) > 0, waiting - pending, want)

    best = _best_task_at(block, classify_at, pos, scorer)

    # Fetch what the block needs but this unit is not carrying. A shed trip is
    # only worth making when something is waiting at the other end.
    if best is None or best[0] > T_SETUP:
        for c in empty_structs:
            want = animal_of(c)
            if inv.get(want, 0) == 0 and shed.get(want, 0) > 0:
                return _go(pos, _nearest_shed_tile(*pos), ["PICKUP", want, 1])
        if unfed and not has_wheat and wheat_in_shed > 0 and day < SEASON_DAYS - 1:
            return _go(pos, _nearest_shed_tile(*pos),
                       ["PICKUP", "WHEAT", min(FEED_CARRY, wheat_in_shed)])

    if best is None:
        if carried > 0:
            return _go(pos, _nearest_shed_tile(*pos), ["DROP"])
        return ["PASS"]

    _tier, target, op = best
    if op == "PLACE":
        return _go(pos, target, ["PLACE", animal_of(target)])
    if op == "PLANT":
        return _go(pos, target, ["PLANT", "WHEAT"])
    return _go(pos, target, [op])



def _farmhand_op(tiles, pos, block, fallback, day, hour, carried, seeds_left,
                 crop_of, rush=False, scorer=None):
    """One op for a unit working crops."""
    # Get produce into the shed while it can still be sold. Anything still in a
    # unit's hands when the season ends is scored as nothing, and any wave
    # bigger than the shed cap is discarded at end of day.
    flush_hour = FLUSH_HOUR if day >= SEASON_DAYS - 1 else DAILY_FLUSH_HOUR
    last_day_flush = (hour >= flush_hour or rush) and carried > 0
    if carried >= DROP_THRESHOLD or last_day_flush:
        return _go(pos, _nearest_shed_tile(*pos), ["DROP"]), 0

    def classify_at(xy):
        crop = crop_of(xy)
        got = _crop_task(tiles[xy[1]][xy[0]], day, crop)
        if got is not None and got[1] == "PLANT" and seeds_left.get(crop, 0) <= 0:
            return None
        return got

    best = _best_task_at(block, classify_at, pos, scorer)
    if best is None:
        best = _best_task_at(fallback, classify_at, pos, scorer)
    if best is None:
        return ["PASS"], None

    _tier, target, op = best
    if op == "PLANT":
        crop = crop_of(target)
        return _go(pos, target, ["PLANT", crop]), (crop if tuple(pos) == target else None)
    return _go(pos, target, [op]), None


def _hire_cost(k):
    """What hiring k hands in one morning costs.

    The n-th hire of a day costs `fib(n)` and the count resets every morning,
    so k hands cost 1, 2, 4, 7, 12, 20, 33, 54, 88, 143 cumulatively.
    """
    a, b, total = 1, 1, 0
    for _ in range(k):
        total += a
        a, b = b, a + b
    return total


def _hire_target(full_plot, n_animal_tiles, active_tiles=None, money=None):
    """Crew size: ranchers for the animal zone, plus hands for the crops.

    Sizing the crew off tile count alone ignored that a goose needs about 3.5
    actions a day. At a large flock the ranchers ate the entire crew, nobody
    planted, and the score collapsed to a third of its value.

    `active_tiles` is the work that exists right now -- tiles carrying a plant
    or an animal, plus bare ones we hold seed for -- rather than every tile we
    happen to own. A hand hired against ground we cannot plant yet idles all
    day and still charges for it.

    `money` caps the crew at what the morning can actually afford, keeping
    `HIRE_CASH_BUFFER` back for seed. Without it the farm hires itself broke
    before its first income lands.
    """
    ranchers = (n_animal_tiles + GEESE_PER_RANCHER - 1) // GEESE_PER_RANCHER
    if HIRE_TO_WORK and active_tiles is not None:
        workable = max(0, active_tiles - n_animal_tiles)
        croppers = (workable + TILES_PER_UNIT - 1) // TILES_PER_UNIT
    else:
        croppers = max(0, len(full_plot) - n_animal_tiles) // TILES_PER_UNIT
    want = min(MAX_HANDS, max(1, MIN_HANDS, ranchers + croppers - 1))
    if HIRE_TO_WORK and money is not None:
        while want > 1 and _hire_cost(want) > max(0, money - HIRE_CASH_BUFFER):
            want -= 1
    # Never hire the farm broke. This is a floor on solvency, not a policy:
    # hiring used to read no balance at all, so `MIN_HANDS>=8` paid ~$54/day
    # through the days 0-10 window when the bank holds ~$300 and nothing earns
    # until melon on day 11 -- broke by day 9, and then BUY_SEED fires twice in
    # a whole game and BUY_ANIMAL never. Final bank $0.
    #
    # The cap is a *share* of the balance rather than a fixed reserve. A fixed
    # reserve was tried and it throttles the healthy case instead of catching
    # the sick one: against an early bank of $300 a $400 buffer forces the crew
    # to one hand and costs $9k. A quarter of the bank leaves the default
    # untouched (six hands cost $20 against a $120 balance) and still degrades
    # smoothly as the farm runs down.
    if money is not None:
        while want > 1 and _hire_cost(want) > max(1.0, HIRE_BANK_SHARE * money):
            want -= 1
    return want


def _sell_qty(item, count, day, shed_total):
    """How much of `item` to offer this turn.

    Everything not metered is dumped, which is what a race good wants. A
    metered good goes out a slice at a time so the wave does not eat its own
    price -- except when the season is nearly over and unsold stock is about
    to score zero, or when the shed is full enough that end-of-day overflow
    would destroy more than the drip protects.
    """
    if not SELL_METER or item not in METERED:
        return count
    if day >= METER_LAST_DAY or shed_total > METER_SHED_LIMIT:
        return count
    return min(count, SELL_CHUNK)


def _market_orders(me, private, obs, full_plot, crop_plot, n_geese, n_animal_tiles,
                   crop_of, placeable_by_kind, melon_switch=False,
                   view=None):
    """Hire, expand, sell the surplus, restock -- in that order.

    Order matters: the queue is capped at `maxMarketOrdersPerTurn` and is
    processed in sequence, and SELL has to come before any BUY because a full
    shed makes buying fail.
    """
    orders = []
    day = obs["day"]
    hour = obs["hour"]
    money = me["money"]
    shed = private.get("shed", {}) or {}
    seeds = private.get("seeds", {}) or {}

    # Hire at the top of the day, before there is work to fall behind on.
    # Hands last one day, so this repeats every morning.
    if hour <= 1 and day <= SEASON_DAYS - 2:
        # Work that exists this morning: anything already growing or grazing,
        # plus bare ground we are actually holding seed for.
        active = 0
        budget = max(0, money - LAND_CASH_BUFFER)
        for (ax, ay) in full_plot:
            tile = me["tiles"][ay][ax]
            if isinstance(tile, dict):
                active += 1  # already growing or grazing: it needs tending
                continue
            if tile is not None:
                continue
            # Bare. It is work today only if a seed can actually go in it, and
            # hiring runs at hour 0-1 *before* the seed orders in this same
            # queue are filled -- so ground we can afford counts, not just
            # ground we already hold seed for. Missing this under-hires on the
            # day the melon money lands and the farm plants out all at once,
            # which is the one day that must not be slowed down.
            zone = crop_of((ax, ay))
            if seeds.get(zone, 0) > 0:
                active += 1
                continue
            cost = CROP_SPEC.get(zone, CROP_SPEC["WHEAT"])["seed"]
            if budget >= cost:
                budget -= cost
                active += 1
        want = _hire_target(full_plot, n_animal_tiles, active, money)
        for _ in range(max(0, want - me.get("hires_today", 0))):
            orders.append(["HIRE"])

    # Land, unless the herd is being bought first. The 804-rated ladder build
    # places cows on day 0 and buys its quadrants on days 6 and 8; this one
    # queues BUY_LAND ahead of BUY_ANIMAL, so day 0 spends $1,000 on NE and the
    # rest on melon seed and the first cow waits for melon money on day 11. A
    # cow yields eight days after placement, so that is eleven days of milk
    # given away -- 146 units a game against their 273.
    def _land_order():
        bought = len(me.get("unlocked_quadrants", ["NW"])) - 1
        if (bought < min(MAX_LAND, len(LAND_PRICES))
                and day <= SEASON_DAYS - 8 and day >= LAND_START_DAY):
            if money >= LAND_PRICES[bought] + LAND_CASH_BUFFER:
                return ["BUY_LAND"], LAND_PRICES[bought]
        return None, 0

    land_order = None
    if not HERD_FIRST:
        land_order, spent = _land_order()
        if land_order:
            orders.append(land_order)
            money -= spent

    # Sell everything except the feed reserve. Wheat and egg are `log` sinks --
    # they hold ~$20 and ~$40 at any volume we can reach -- so there is nothing
    # to gain by holding, and the shed's 100-item cap silently discards the
    # overflow if we do.
    # Feed is bought, not farmed. A goose eats one wheat a day and returns
    # roughly $140, so paying ~$25 on the market for feed is never the
    # question -- and gating the flock on our own harvest capped it at eight
    # birds, because the reserve we held back was exactly the surplus the
    # purchase test was looking for.
    reserve = n_geese * FEED_RESERVE_PER_GOOSE if day < SEASON_DAYS - 1 else 0
    shed_total = sum(v for k, v in shed.items() if k not in ANIMAL_SPEC)
    for item, count in shed.items():
        # Animals are not products: the environment only fills a SELL whose
        # item is in PRODUCTS, and drops the order otherwise -- but it still
        # costs one of the ten market orders this turn. The guard here named
        # GOOSE and was never updated when the herd became cows and sheep, so
        # every turn with an unplaced animal in the shed threw away a slot,
        # and the seed orders at the end of the queue are what got truncated.
        if count <= 0 or item in ANIMAL_SPEC:
            continue
        sellable = count - reserve if item == "WHEAT" else count
        sellable = _sell_qty(item, sellable, day, shed_total)
        if sellable > 0:
            orders.append(["SELL", item, sellable])

    # The herd, as fast as cash allows. Sheep first, then cows: sheep return
    # the most per tile per day, and an animal bought early compounds for the
    # rest of the season. Payback is under two days for both.
    if GOOSE_START_DAY <= day <= LAST_GOOSE_DAY:
        # Buy the animal whose product is worth most at projected prices, not
        # the one a sweep picked. Wool and milk diverge hard: wool is `sq`
        # above I0 with T=105 and floors on a glut, milk is `linear` with
        # T=122 and the town drains it 19/day, so which one is worth having
        # depends on what is already in both farms' pastures.
        order = ("SHEEP", "COW", "GOOSE")
        if ADAPTIVE_HERD and view is not None:
            order = tuple(sorted(order, key=lambda k: -_animal_rate(view, k)))
        for kind in order:
            quota = placeable_by_kind.get(kind, 0) - shed.get(kind, 0)
            if quota <= 0:
                continue
            cost = ANIMAL_SPEC[kind]["cost"]
            affordable = int(max(0, money - GOOSE_CASH_BUFFER) // cost)
            want = min(quota, affordable, GOOSE_BUY_RATE)
            if want > 0:
                orders.append(["BUY_ANIMAL", kind, want])
                money -= want * cost

    # Herd first: land only gets what the animals did not need. Delaying land
    # also ramps the crew for free -- `_hire_target` sizes croppers off tiles
    # owned, so a farm that is still one quadrant hires four hands, not nine,
    # which is exactly the 4 -> 11 curve the 804 build shows across days 0-9.
    if HERD_FIRST:
        land_order, spent = _land_order()
        if land_order:
            orders.append(land_order)
            money -= spent

    short_feed = reserve - shed.get("WHEAT", 0)
    if FEED_BUY and short_feed > 0 and day < SEASON_DAYS - 1:
        room_in_shed = SHED_CAPACITY - sum(v for v in shed.values() if v > 0)
        affordable = int(max(0, money - GOOSE_CASH_BUFFER) // 60)
        want = min(short_feed, room_in_shed, affordable)
        if want > 0:
            orders.append(["BUY_PRODUCT", "WHEAT", want])

    # Premium first, then feed. Spend against a running balance: without it
    # each crop sized its order off the full bank, and once strawberry joined
    # melon the three orders together emptied the account on day 0 -- no cash
    # to hire, one farmer for 23 tiles, the whole farm dead by day 3.
    def zoned(xy):
        """What a bare tile will actually be planted with, for seed demand.

        Seeds used to be bought against the *zoning*, so switching the melon
        block to strawberry would have bought melon seed for tiles that never
        take it and left the strawberry short.
        """
        got = crop_of(xy)
        if melon_switch and got == "MELON":
            return "STRAWBERRY"
        return got

    stranded = 0  # bare tiles whose zoned crop is unaffordable or out of time
    for crop in ("MELON", "STRAWBERRY"):
        bare = sum(1 for xy in crop_plot
                   if me["tiles"][xy[1]][xy[0]] is None and zoned(xy) == crop)
        bridgeable = BRIDGE_MELON or crop != "MELON"
        if day > _last_plant_day(crop):
            if BRIDGE_LATE and bridgeable:
                stranded += bare  # nothing of this crop will ever go in again
            continue
        short = bare - seeds.get(crop, 0)
        cost = CROP_SPEC[crop]["seed"]
        affordable = int(max(0, money - LAND_CASH_BUFFER) // cost)
        want = max(0, min(short, affordable))
        if want > 0:
            orders.append(["BUY_SEED", crop, want])
            money -= want * cost
        if BRIDGE_EARLY and bridgeable:
            stranded += max(0, short - want)  # could not fund it this turn

    # Wheat last, on whatever is left: its own zoned tiles plus the bridge.
    # It buys against BRIDGE_CASH_BUFFER rather than LAND_CASH_BUFFER, because
    # the $300 land buffer is exactly what strands the first ten days -- and
    # land and animals are already queued ahead of this, so they get their cut
    # first whatever is left here.
    bare_wheat = sum(1 for xy in crop_plot
                     if me["tiles"][xy[1]][xy[0]] is None and zoned(xy) == "WHEAT")
    if BRIDGE_EARLY or BRIDGE_LATE:
        bare_wheat += stranded
        buffer = BRIDGE_CASH_BUFFER
    else:
        buffer = LAND_CASH_BUFFER
    if bare_wheat > 0 and day <= _last_plant_day("WHEAT"):
        short = bare_wheat - seeds.get("WHEAT", 0)
        affordable = int(max(0, money - buffer) // WHEAT_SEED_COST)
        want = min(short, affordable)
        if want > 0:
            orders.append(["BUY_SEED", "WHEAT", want])
            money -= want * WHEAT_SEED_COST

    return orders[:MAX_MARKET_ORDERS]


def agent(obs):
    player = obs["player"]
    me = obs["farms"][player]
    private = obs["private"]
    tiles = me["tiles"]
    day = obs["day"]
    hour = obs["hour"]

    hands = me.get("hands", []) or []
    units = [tuple(me["farmer"])] + [tuple(p) for p in hands]
    n_units = len(units)

    # The tiles nearest the shed become the animal zone: feed comes out of the
    # shed every day, so a long walk there is paid over and over.
    full_plot = (_planned_tiles(tiles, MAX_LAND) if PLANNED_ZONES
                 else _workable_tiles(tiles))
    animal_zone = full_plot[:GOOSE_TARGET]

    # One market read a turn, shared by the herd and planting decisions.
    view = None
    if ADAPTIVE_CROP or ADAPTIVE_HERD:
        view = _market_view(obs, player)

    # Zone the herd: sheep nearest the shed, then cows, then any geese.
    # Feed comes out of the shed every day, so the walk is paid over and over
    # and the animals worth the most per tile get the shortest one.
    plan = ["SHEEP"] * N_SHEEP + ["COW"] * N_COWS + ["GOOSE"] * N_GEESE
    zoned = {tuple(xy): plan[i] for i, xy in enumerate(animal_zone) if i < len(plan)}

    # Which of cow or sheep is worth more *right now*, decided once a turn.
    #
    # Both stand on a PASTURE, so trading one for the other costs no structure
    # and no action -- which is what makes this cheap enough to do at all. A
    # goose needs a COOP, so geese are never substituted.
    #
    # It matters because the two curves diverge violently. Wool is `sq` above
    # I0 with T=105, milk `linear` with T=122, and the town drains milk 19/day
    # against wool's 13. A pasture zoned for milk while the market is already
    # carrying 400 units of it is worth $22 a day; the same tile as wool is
    # worth $348.
    herd_pick = None
    if ADAPTIVE_HERD and view is not None:
        herd_pick = ("COW" if _animal_rate(view, "COW")
                     >= _animal_rate(view, "SHEEP") else "SHEEP")

    def animal_of(xy):
        base = zoned.get(tuple(xy), "COW")
        if herd_pick is None or base == "GOOSE":
            return base
        tile = tiles[xy[1]][xy[0]]
        if isinstance(tile, dict) and tile.get("animal"):
            return tile["animal"]      # already grazing; it is what it is
        return herd_pick

    n_geese = sum(1 for (x, y) in animal_zone
                  if isinstance(tiles[y][x], dict) and "animal" in tiles[y][x])

    # Tiles an animal could stand on soon: bare ground, or an empty structure
    # of the right kind. Counted per kind so we never buy what cannot be placed;
    # an animal cannot be sold, so one that never lands is its price deleted.
    placeable_by_kind = {}
    for xy in animal_zone:
        t = tiles[xy[1]][xy[0]]
        kind = animal_of(xy)
        if t is None or (isinstance(t, dict) and "animal" not in t
                         and t.get("kind") == ANIMAL_SPEC[kind]["structure"]):
            placeable_by_kind[kind] = placeable_by_kind.get(kind, 0) + 1

    # One rancher per `GEESE_PER_RANCHER` coops, but never the whole crew.
    active = sum(1 for (x, y) in animal_zone if isinstance(tiles[y][x], dict))
    n_ranchers = min(max(1, n_units - 1),
                     (active + GEESE_PER_RANCHER - 1) // GEESE_PER_RANCHER)
    if day <= LAST_GOOSE_DAY and active < len(animal_zone):
        n_ranchers = max(n_ranchers, 1)  # somebody has to build the coops

    # Melon sits just outside the animal zone: it needs no shed trips, only
    # daily water, so distance from the shed costs it little.
    # Wheat gets its ground *first* when WHEAT_FIRST_TILES is set, ahead of
    # melon rather than out of the leftovers.
    #
    # Zoning runs animals -> melon -> strawberry -> whatever is left, and on
    # day 0 only NW is unlocked, so the 24-tile melon zone swallows the whole
    # board and wheat gets nothing until the second quadrant lands. That is
    # survivable while land is bought on day 0 and melon is the cash engine.
    # It is fatal to a herd-first opening: the 804 build has wheat on tiles
    # from day 0 and melon only from day 4, because with the herd bought first
    # there is no money left for melon seed and wheat -- four days to harvest
    # against melon's ten -- is what pays for the season.
    w0 = len(animal_zone)
    wheat_zone = set(full_plot[w0:w0 + WHEAT_FIRST_TILES])
    m0 = w0 + WHEAT_FIRST_TILES
    melon_zone = set(full_plot[m0:m0 + MELON_TILES])
    s0 = m0 + MELON_TILES
    berry_zone = set(full_plot[s0:s0 + STRAWBERRY_TILES])

    def crop_of(xy):
        xy = tuple(xy)
        if xy in wheat_zone:
            return "WHEAT"
        if xy in melon_zone:
            return "MELON"
        if xy in berry_zone:
            return "STRAWBERRY"
        return "WHEAT"

    n_crop_units = max(0, n_units - n_ranchers)
    crop_plot = full_plot[len(animal_zone):][: TILES_PER_UNIT * max(1, n_crop_units)]
    # Never leave melon ground unworked: it outearns wheat many times over.
    for xy in wheat_zone | melon_zone | berry_zone:
        if xy not in crop_plot:
            crop_plot.append(xy)

    rancher_blocks = _territories(animal_zone, max(1, n_ranchers))
    crop_blocks = _territories(crop_plot, max(1, n_crop_units))

    shed = private.get("shed", {}) or {}
    wheat_in_shed = shed.get("WHEAT", 0)
    seeds_left = dict(private.get("seeds", {}) or {})

    wheat_last = _last_plant_day("WHEAT")

    # Melon dies for good the moment our own first cycle lands; strawberry
    # climbs all season. Past the point where melon is worth less than the
    # strawberry that could replace it, replant the block.
    melon_switch = bool(
        MELON_SWITCH
        and obs["market"]["prices"].get("MELON", 250) < MELON_SWITCH_PRICE
        and day <= _last_plant_day("STRAWBERRY"))

    def plant_crop_of(xy):
        """What to actually put in a bare tile *now*.

        `crop_of` is the zoning and does not change; this is the planting
        decision. A tile whose zoned crop cannot go in -- no seed and no cash
        for one in the first ten days, or past its last-plant day in the last
        eight -- carries a wheat cycle instead of sitting bare.
        """
        crop = crop_of(xy)
        # Melon ground, once melon is dead, is just the best-watered land on
        # the farm. Strawberry is an ongoing crop -- one plant action and then
        # only survival watering -- so a switch this late still collects two
        # to four yields into a market that is climbing.
        if melon_switch and crop == "MELON":
            return "STRAWBERRY"
        # Adaptive substitution: plant whatever the projected prices say is
        # worth most per tile-day, provided it beats the zoned crop by enough
        # to be worth the churn. This is what makes the second melon cycle a
        # decision rather than a constant -- if their melon is ripening, ours
        # is worth the floor and the tile goes to strawberry instead.
        if ADAPTIVE_CROP and view is not None:
            best, best_rate = crop, _crop_rate(view, crop) * ADAPTIVE_MARGIN
            for alt in ("MELON", "STRAWBERRY", "WHEAT"):
                if alt == crop or day > _last_plant_day(alt):
                    continue
                rate = _crop_rate(view, alt)
                if rate > best_rate:
                    best, best_rate = alt, rate
            return best
        if crop == "WHEAT" or day > wheat_last or seeds_left.get("WHEAT", 0) <= 0:
            return crop
        if crop == "MELON" and not BRIDGE_MELON:
            return crop
        if BRIDGE_LATE and day > _last_plant_day(crop):
            return "WHEAT"
        if BRIDGE_EARLY and seeds_left.get(crop, 0) <= 0:
            return "WHEAT"
        return crop
    inventories = private.get("inventories", []) or [{}]

    # Is the opponent about to dump melon? Their tiles are public.
    rush = False
    if FRONT_RUN and len(obs["farms"]) > 1:
        them = obs["farms"][1 - player]
        ripe = CROP_SPEC["MELON"]["harvest_age"]
        for row in them["tiles"]:
            for t in row:
                if (isinstance(t, dict) and t.get("kind") == "PLANT"
                        and t.get("crop") == "MELON"
                        and day - t.get("planted_day", day) >= ripe - 1):
                    rush = True
                    break
            if rush:
                break

    # One forward pass a turn serves the whole crew: the policy scores every
    # cell, and each unit reads the cell it stands on.
    pol = _policy()
    board = None
    planes = None
    if pol is not None or DAGGER_CAPTURE:
        try:
            import nn_features as _nf
            planes = _nf.encode(obs, player)
            if pol is not None:
                board = pol.trunk(planes)
        except Exception as exc:
            # Falling back silently is how a stale checkpoint once looked like
            # a perfect clone: weights trained on 41 planes met a 46-plane
            # encoder, the load failed, the agent ran pure heuristic, and the
            # results were byte-identical to it. Say so, once, on stderr --
            # a submitted agent still must not die here.
            global _POLICY_WARNED
            if not _POLICY_WARNED:
                _POLICY_WARNED = True
                import sys as _s
                print("policy disabled: %s: %s" % (type(exc).__name__, exc),
                      file=_s.stderr)
            board, planes = None, None

    ops = []
    _expert = []
    del _LAST_TARGET[:]
    for i, pos in enumerate(units):
        inv = inventories[i] if i < len(inventories) and isinstance(inventories[i], dict) else {}
        carried = sum(inv.values())
        # The learned policy scores every cell as a destination for *this*
        # unit; the router then picks the best-scoring cell that actually has
        # work on it. Choosing among real jobs is the part worth learning.
        scorer = None
        if board is not None:
            _sc = pol.scores(board, int(pos[0]), int(pos[1]))
            scorer = lambda tx, ty, _s=_sc: float(_s[ty, tx])

        if i < n_ranchers:
            ops.append(_rancher_op(tiles, pos, rancher_blocks[i], day, hour, inv,
                                   carried, shed, wheat_in_shed, animal_of,
                                   rush and inv.get("MELON", 0) > 0, scorer))
        else:
            block = crop_blocks[i - n_ranchers] if n_crop_units else []
            op, used = _farmhand_op(tiles, pos, block, crop_plot, day, hour,
                                    carried, seeds_left, plant_crop_of,
                                    rush and inv.get("MELON", 0) > 0, scorer)
            if used:
                seeds_left[used] = seeds_left.get(used, 0) - 1
            ops.append(op)

        # The policy proposes; the tile disposes. An illegal action is
        # silently dropped by the environment, which costs the unit its turn,
        # so anything that does not pass falls through to the next-best op and
        # then to the heuristic already in `ops[-1]`.
        # The heuristic's answer for this exact state, before anything
        # overrides it. This is the DAgger label, and it is why the expert
        # never has to be queried separately: it has already run.
        _heur_op = ops[-1]
        if DAGGER_CAPTURE and planes is not None:
            # The cell the router sent this unit to, which is the label. If it
            # acted in place, the target is where it stands.
            tgt = _LAST_TARGET[-1] if _LAST_TARGET else tuple(pos)
            _expert.append((int(pos[1]), int(pos[0]), _heur_op, carried,
                            int(tgt[1]), int(tgt[0])))

    if DAGGER_CAPTURE and planes is not None and _expert:
        DAGGER_LOG.append((planes, _expert))

    market = _market_orders(me, private, obs, full_plot, crop_plot, n_geese,
                            len(animal_zone), crop_of, placeable_by_kind,
                            melon_switch, view)
    return {"farmer": ops[0], "hands": ops[1:], "market": market}
