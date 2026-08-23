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
import os

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
CROP_SPEC = {
    "WHEAT": {"seed": 10, "harvest_age": 4, "window": (2, 4)},
    "MELON": {"seed": 80, "harvest_age": 10, "window": (6, 10)},
    # Ongoing: produces at ages 10, 12, 14, 16 and then decays, so it is
    # harvested repeatedly and never replanted. Watering earns no yield bonus
    # on an ongoing crop, so it is watered only to keep it alive. The town
    # drains strawberry 25/day, more than any other product, which is why the
    # price holds despite a curve that would otherwise floor it by unit 60.
    "STRAWBERRY": {"seed": 100, "harvest_age": 10, "window": (99, 0),
                   "ongoing": True},
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

# The herd, on the tiles nearest the shed. Sized against what the town drains
# per day, since that is what holds the price up.
N_SHEEP = _P("N_SHEEP", 4)
N_COWS = _P("N_COWS", 8)
N_GEESE = _P("N_GEESE", 0)
GOOSE_TARGET = N_SHEEP + N_COWS + N_GEESE  # total animal tiles
GEESE_PER_RANCHER = _P("GEESE_PER_RANCHER", 5)
# Geese bought before the wheat engine runs simply starve: there is no feed in
# the shed and no cash left to buy any. Hold back enough to keep planting.
GOOSE_CASH_BUFFER = _P("GOOSE_CASH_BUFFER", 700)
GOOSE_START_DAY = _P("GOOSE_START_DAY", 3)
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
FEED_BUY = _P("FEED_BUY", 1)

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

# How to order tiles before splitting them into per-unit blocks.
#   0 = by distance from the shed. Tiles at equal distance lie on a diagonal,
#       so a "contiguous" chunk is an arc spanning the whole quadrant.
#   1 = serpentine rows, which keeps consecutive tiles genuinely adjacent.
BLOCK_ORDER = _P("BLOCK_ORDER", 1)


# Let an idle unit do the other role's work instead of passing.
# Territories are fixed for the day, so a unit whose own zone has nothing
# actionable stands still: the herd needs far fewer actions than its ranchers
# have, and melon and strawberry leave a crop block dormant for days at a time.
CROSS_HELP = _P("CROSS_HELP", 0)

# Tiles given over to melon, taken just outside the animal zone. The market
# pays $21,721 for the first 100 melons and almost nothing past 150, and the
# town drains only one a day, so this is a race against the opponent rather
# than a production problem: plant early, sell on harvest. Swept at 24, and
# bracketed: 16 loses to it 3-21, and 30, 36 and 44 all lose to it 0-24.
# The old value of 16 was fitted when the spare land grew wheat.
MELON_TILES = _P("MELON_TILES", 24)
MELON_LAST_PLANT = _P("MELON_LAST_PLANT", 19)

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
STRAWBERRY_TILES = _P("STRAWBERRY_TILES", 44)

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
    """What a crop tile needs, or None. `crop` is what this tile is zoned for."""
    last_day = day >= SEASON_DAYS - 1
    if tile is None:
        if last_day or day > _last_plant_day(crop):
            return None
        return (T_PLANT, "PLANT")
    if not isinstance(tile, dict):
        return None
    kind = tile.get("kind")
    if kind == "PLANT":
        age = day - tile.get("planted_day", day)
        spec = CROP_SPEC.get(tile.get("crop"), CROP_SPEC["WHEAT"])
        ripe = spec["harvest_age"]
        if tile.get("yield_units", 0) > 0 and (age >= ripe or last_day):
            return (T_HARVEST, "HARVEST")
        # On the last day a plant that cannot be harvested is worth nothing,
        # and watering it is an action not spent converting stock to cash.
        if last_day:
            return None
        if _needs_water(tile, day):
            # A plant one dry day from death outranks everything else; a plant
            # merely missing yield does not.
            dying = tile.get("consecutive_unwatered", 0) >= 1
            return (T_RESCUE if dying else T_WATER, "WATER")
        return None
    if kind == "WEED":
        return None if last_day else (T_DIG, "DIG")
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
            return (T_SETUP, spec["build"])
        return _crop_task(tile, day)
    if not isinstance(tile, dict):
        return None
    if "animal" not in tile:
        if day >= SEASON_DAYS - 1:
            return None  # placing an animal now earns nothing
        if tile.get("kind") == spec["structure"]:
            return (T_SETUP, "PLACE") if has_animal else None
        # A crop or a weed squatting on the animal zone; treat it normally.
        return _crop_task(tile, day)

    last_day = day >= SEASON_DAYS - 1
    held = tile.get("yield_units", 0)
    max_held = ANIMAL_SPEC[tile["animal"]]["max_held"]

    # Escaping costs the whole animal -- $400 for a cow, $500 for a sheep -- so
    # feeding a hungry one beats everything. It still produces while unfed; it
    # does not survive two days.
    if tile.get("consecutive_unfed", 0) >= 1 and not tile.get("fed_today") and has_wheat:
        return (T_RESCUE, "FEED")
    # At max_held, tonight's production is thrown away. Harvest also returns the
    # whole stack for one action, which makes it the best action available.
    if held >= max_held or (last_day and held > 0):
        return (T_HARVEST_FULL, "HARVEST")
    # One action for ~$80, available daily whether or not the animal was fed.
    if tile.get("fertilizer_available"):
        return (T_FERT, "COLLECT_FERTILIZER")
    if not tile.get("fed_today") and has_wheat and not last_day:
        return (T_FEED, "FEED")
    if held >= max_held - 1:
        return (T_HARVEST, "HARVEST")
    # CARE banks +1 for the next production, but only pays out on a fed day.
    if (CARE_ENABLED and tile.get("fed_today")
            and not tile.get("cared_today") and not last_day):
        return (T_CARE, "CARE")
    if held > 0:
        return (T_HARVEST, "HARVEST")
    return None



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
        tier, op = got
        dist = TIEBREAK_DIST * (abs(tx - pos[0]) + abs(ty - pos[1]))
        key = (tier * URGENCY_W + dist, tier, dist)
        if best is None or key < best[0]:
            best = (key, (tx, ty), op)
    if best is None:
        return None
    _cost, tier, _dist = best[0]
    target, op = best[1], best[2]
    return (tier, target, op)


def _best_task_at(block, classify_at, pos):
    """As `_best_task`, but the classifier sees the position so it can look up
    which crop that tile is zoned for."""
    best = None
    for (tx, ty) in block:
        got = classify_at((tx, ty))
        if got is None:
            continue
        tier, op = got
        dist = TIEBREAK_DIST * (abs(tx - pos[0]) + abs(ty - pos[1]))
        key = (tier * URGENCY_W + dist, tier, dist)
        if best is None or key < best[0]:
            best = (key, (tx, ty), op)
    if best is None:
        return None
    _cost, tier, _dist = best[0]
    target, op = best[1], best[2]
    return (tier, target, op)


def _go(pos, target, op_here):
    if tuple(pos) == tuple(target):
        return op_here
    return [_step_toward(pos[0], pos[1], target[0], target[1])]


def _rancher_op(tiles, pos, block, day, hour, inv, carried, shed,
                wheat_in_shed, animal_of, rush=False):
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

    best = _best_task_at(block, classify_at, pos)

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
                 crop_of, rush=False):
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

    best = _best_task_at(block, classify_at, pos)
    if best is None:
        best = _best_task_at(fallback, classify_at, pos)  # its own block is idle
    if best is None:
        return ["PASS"], None

    _tier, target, op = best
    if op == "PLANT":
        crop = crop_of(target)
        return _go(pos, target, ["PLANT", crop]), (crop if tuple(pos) == target else None)
    return _go(pos, target, [op]), None


def _hire_target(full_plot, n_animal_tiles):
    """Crew size: ranchers for the animal zone, plus hands for the crops.

    Sizing the crew off tile count alone ignored that a goose needs about 3.5
    actions a day. At a large flock the ranchers ate the entire crew, nobody
    planted, and the score collapsed to a third of its value.
    """
    ranchers = (n_animal_tiles + GEESE_PER_RANCHER - 1) // GEESE_PER_RANCHER
    croppers = max(0, len(full_plot) - n_animal_tiles) // TILES_PER_UNIT
    return min(MAX_HANDS, max(1, MIN_HANDS, ranchers + croppers - 1))


def _market_orders(me, private, obs, full_plot, crop_plot, n_geese, n_animal_tiles,
                   crop_of, placeable_by_kind):
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
        want = _hire_target(full_plot, n_animal_tiles)
        for _ in range(max(0, want - me.get("hires_today", 0))):
            orders.append(["HIRE"])

    bought = len(me.get("unlocked_quadrants", ["NW"])) - 1
    if bought < min(MAX_LAND, len(LAND_PRICES)) and day <= SEASON_DAYS - 8:
        if money >= LAND_PRICES[bought] + LAND_CASH_BUFFER:
            orders.append(["BUY_LAND"])

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
    for item, count in shed.items():
        if count <= 0 or item == "GOOSE":
            continue
        sellable = count - reserve if item == "WHEAT" else count
        if sellable > 0:
            orders.append(["SELL", item, sellable])

    # The herd, as fast as cash allows. Sheep first, then cows: sheep return
    # the most per tile per day, and an animal bought early compounds for the
    # rest of the season. Payback is under two days for both.
    if GOOSE_START_DAY <= day <= LAST_GOOSE_DAY:
        for kind in ("SHEEP", "COW", "GOOSE"):
            quota = placeable_by_kind.get(kind, 0) - shed.get(kind, 0)
            if quota <= 0:
                continue
            cost = ANIMAL_SPEC[kind]["cost"]
            affordable = int(max(0, money - GOOSE_CASH_BUFFER) // cost)
            want = min(quota, affordable, GOOSE_BUY_RATE)
            if want > 0:
                orders.append(["BUY_ANIMAL", kind, want])
                money -= want * cost

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
    for crop in ("MELON", "STRAWBERRY", "WHEAT"):
        if day > _last_plant_day(crop):
            continue
        bare = sum(1 for xy in crop_plot
                   if me["tiles"][xy[1]][xy[0]] is None and crop_of(xy) == crop)
        short = bare - seeds.get(crop, 0)
        cost = CROP_SPEC[crop]["seed"]
        affordable = int(max(0, money - LAND_CASH_BUFFER) // cost)
        want = min(short, affordable)
        if want > 0:
            orders.append(["BUY_SEED", crop, want])
            money -= want * cost

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
    full_plot = _workable_tiles(tiles)
    animal_zone = full_plot[:GOOSE_TARGET]

    # Zone the herd: sheep nearest the shed, then cows, then any geese.
    # Feed comes out of the shed every day, so the walk is paid over and over
    # and the animals worth the most per tile get the shortest one.
    plan = ["SHEEP"] * N_SHEEP + ["COW"] * N_COWS + ["GOOSE"] * N_GEESE
    zoned = {tuple(xy): plan[i] for i, xy in enumerate(animal_zone) if i < len(plan)}

    def animal_of(xy):
        return zoned.get(tuple(xy), "COW")

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
    m0 = len(animal_zone)
    melon_zone = set(full_plot[m0:m0 + MELON_TILES])
    s0 = m0 + MELON_TILES
    berry_zone = set(full_plot[s0:s0 + STRAWBERRY_TILES])

    def crop_of(xy):
        xy = tuple(xy)
        if xy in melon_zone:
            return "MELON"
        if xy in berry_zone:
            return "STRAWBERRY"
        return "WHEAT"

    n_crop_units = max(0, n_units - n_ranchers)
    crop_plot = full_plot[len(animal_zone):][: TILES_PER_UNIT * max(1, n_crop_units)]
    # Never leave melon ground unworked: it outearns wheat many times over.
    for xy in melon_zone | berry_zone:
        if xy not in crop_plot:
            crop_plot.append(xy)

    rancher_blocks = _territories(animal_zone, max(1, n_ranchers))
    crop_blocks = _territories(crop_plot, max(1, n_crop_units))

    shed = private.get("shed", {}) or {}
    wheat_in_shed = shed.get("WHEAT", 0)
    seeds_left = dict(private.get("seeds", {}) or {})
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

    ops = []
    for i, pos in enumerate(units):
        inv = inventories[i] if i < len(inventories) and isinstance(inventories[i], dict) else {}
        carried = sum(inv.values())
        hurry = rush and inv.get("MELON", 0) > 0
        used = None
        if i < n_ranchers:
            op = _rancher_op(tiles, pos, rancher_blocks[i], day, hour, inv,
                             carried, shed, wheat_in_shed, animal_of, hurry)
            # A rancher whose herd is fed, cared for and harvested has nothing
            # left in its zone and used to PASS for the rest of the turn.
            if CROSS_HELP and op == ["PASS"]:
                alt, used = _farmhand_op(tiles, pos, crop_plot, crop_plot, day,
                                         hour, carried, seeds_left, crop_of, hurry)
                if alt == ["PASS"]:
                    used = None
                else:
                    op = alt
        else:
            block = crop_blocks[i - n_ranchers] if n_crop_units else []
            op, used = _farmhand_op(tiles, pos, block, crop_plot, day, hour,
                                    carried, seeds_left, crop_of, hurry)
            # The reverse case: melon and strawberry hold a tile for ten days,
            # so mid-season the whole crop plot can be planted and watered.
            if CROSS_HELP and op == ["PASS"]:
                alt = _rancher_op(tiles, pos, animal_zone, day, hour, inv,
                                  carried, shed, wheat_in_shed, animal_of, hurry)
                if alt != ["PASS"]:
                    op = alt
        if used:
            seeds_left[used] = seeds_left.get(used, 0) - 1
        ops.append(op)

    market = _market_orders(me, private, obs, full_plot, crop_plot, n_geese,
                            len(animal_zone), crop_of, placeable_by_kind)
    return {"farmer": ops[0], "hands": ops[1:], "market": market}
