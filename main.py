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
WHEAT_SEED_COST = 10
WHEAT_MAX_YIELD_DAY = 4
WHEAT_WINDOW_START = (WHEAT_MAX_YIELD_DAY + 1) // 2  # 2
GOOSE_COST = 300
GOOSE_MAX_HELD = 4
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

# How many quadrants to buy. Land comes straight off the final score, and the
# third quadrant costs $4,000 -- swept at $12,502 for two against $9,405 for
# three, so it never earns that back in the days it has left.
MAX_LAND = _P("MAX_LAND", 2)
LAND_CASH_BUFFER = _P("LAND_CASH_BUFFER", 300)

# Coops to aim for, on the tiles nearest the shed. Swept: 18 beats 16 and
# collapses past 24, where geese crowd out the wheat that feeds them.
GOOSE_TARGET = _P("GOOSE_TARGET", 18)
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
FEED_BUY = _P("FEED_BUY", 0)

# Carry this much before making a shed trip. Harvests arrive in waves, and a
# wave larger than the 100-item shed cap is silently discarded at end of day.
DROP_THRESHOLD = _P("DROP_THRESHOLD", 14)

# Weight on distance when breaking ties within an urgency tier. 0 makes a
# unit work its block in a fixed order regardless of where it is standing.
TIEBREAK_DIST = _P("TIEBREAK_DIST", 1)

# Wheat planted later than this cannot reach max_yield_day before the season
# ends, so the tile is better left empty.
LAST_PLANT_DAY = SEASON_DAYS - 1 - WHEAT_MAX_YIELD_DAY

# Tier ordering for tasks. Lower is more urgent.
T_RESCUE = 0    # dies or escapes tonight if untouched
T_SETUP = 1     # a goose not yet earning is the most expensive idle asset
T_FERT = 2      # ~$80 for one action, the best single action in the game
T_HARVEST = 3
T_FEED = 4
T_CARE = 5
T_WATER = 6     # yield bonus only; the plant is in no danger
T_PLANT = 7
T_DIG = 8


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
    ordered = sorted(plot, key=lambda t: (_quadrant_rank(*t), _shed_dist(*t)))
    per = max(1, (len(ordered) + len(blocks) - 1) // len(blocks))
    for i, tile in enumerate(ordered):
        blocks[min(len(blocks) - 1, i // per)].append(tile)
    return blocks


def _needs_water(tile, day):
    """Water only when it buys something: survival, or yield.

    A plant dies after two consecutive dry days, so one dry day is free. Inside
    the bonus window each watering is worth a unit of yield, so water there
    regardless. Outside it, water only to keep the plant alive.
    """
    if tile.get("watered_today"):
        return False
    if tile.get("consecutive_unwatered", 0) >= 1:
        return True  # dry again tonight and it is a weed by morning
    age = day - tile.get("planted_day", day)
    return WHEAT_WINDOW_START <= age <= WHEAT_MAX_YIELD_DAY


def _crop_task(tile, day):
    """What a crop tile needs, or None."""
    if tile is None:
        return (T_PLANT, "PLANT") if day <= LAST_PLANT_DAY else None
    if not isinstance(tile, dict):
        return None
    kind = tile.get("kind")
    if kind == "PLANT":
        age = day - tile.get("planted_day", day)
        last_day = day >= SEASON_DAYS - 1
        if tile.get("yield_units", 0) > 0 and (age >= WHEAT_MAX_YIELD_DAY or last_day):
            return (T_HARVEST, "HARVEST")
        if _needs_water(tile, day):
            # A plant one dry day from death outranks everything else; a plant
            # merely missing yield does not.
            dying = tile.get("consecutive_unwatered", 0) >= 1
            return (T_RESCUE if dying else T_WATER, "WATER")
        return None
    if kind == "WEED":
        return (T_DIG, "DIG")
    return None


def _animal_task(tile, day, has_wheat, has_goose, coop_budget):
    """What a tile in the animal zone needs, or None."""
    if tile is None:
        # An empty coop is a dead tile, so only build when a bird is waiting
        # for one. Building twelve on day 1 cost us the whole opening.
        if day <= LAST_GOOSE_DAY and coop_budget > 0:
            return (T_SETUP, "BUILD_COOP")
        return _crop_task(tile, day)
    if not isinstance(tile, dict):
        return None
    if "animal" not in tile:
        if tile.get("kind") == "COOP":
            return (T_SETUP, "PLACE") if has_goose else None
        # A crop or a weed squatting on the animal zone; treat it normally.
        return _crop_task(tile, day)

    last_day = day >= SEASON_DAYS - 1
    held = tile.get("yield_units", 0)

    # Escaping costs the whole $300 animal, so feeding a hungry goose beats
    # everything. It still lays while unfed; it does not survive two days.
    if tile.get("consecutive_unfed", 0) >= 1 and not tile.get("fed_today") and has_wheat:
        return (T_RESCUE, "FEED")
    # One action for ~$80, available every day whether or not it was fed.
    if tile.get("fertilizer_available"):
        return (T_FERT, "COLLECT_FERTILIZER")
    # max_held caps unharvested product, so a full tile is production thrown
    # away tonight.
    if held >= GOOSE_MAX_HELD - 1 or (last_day and held > 0):
        return (T_HARVEST, "HARVEST")
    if not tile.get("fed_today") and has_wheat and not last_day:
        return (T_FEED, "FEED")
    # CARE banks +1 for the next production, but only pays out on a fed day.
    if tile.get("fed_today") and not tile.get("cared_today") and not last_day:
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
        key = (tier, TIEBREAK_DIST * (abs(tx - pos[0]) + abs(ty - pos[1])))
        if best is None or key < best[0]:
            best = (key, (tx, ty), op)
    if best is None:
        return None
    (tier, _dist), target, op = best
    return (tier, target, op)


def _go(pos, target, op_here):
    if tuple(pos) == tuple(target):
        return op_here
    return [_step_toward(pos[0], pos[1], target[0], target[1])]


def _rancher_op(tiles, pos, block, day, inv, carried, geese_in_shed, wheat_in_shed):
    """One op for a unit working the animal zone."""
    has_wheat = inv.get("WHEAT", 0) > 0
    has_goose = inv.get("GOOSE", 0) > 0

    animals = [(x, y) for (x, y) in block
               if isinstance(tiles[y][x], dict) and "animal" in tiles[y][x]]
    empty_coops = [(x, y) for (x, y) in block
                   if isinstance(tiles[y][x], dict)
                   and tiles[y][x].get("kind") == "COOP"
                   and "animal" not in tiles[y][x]]
    unfed = [(x, y) for (x, y) in animals if not tiles[y][x].get("fed_today")]
    starving = [(x, y) for (x, y) in unfed
                if tiles[y][x].get("consecutive_unfed", 0) >= 1]

    # A bird that misses a second day is gone along with its $300, so fetching
    # feed for it outranks anything else this unit could be doing -- including
    # building the coops that were previously starving the flock.
    if starving and not has_wheat and wheat_in_shed > 0 and day < SEASON_DAYS - 1:
        return _go(pos, _nearest_shed_tile(*pos),
                   ["PICKUP", "WHEAT", min(FEED_CARRY, wheat_in_shed)])

    coop_budget = geese_in_shed + inv.get("GOOSE", 0) - len(empty_coops)
    best = _best_task(tiles, block,
                      lambda t: _animal_task(t, day, has_wheat, has_goose, coop_budget),
                      pos)

    # Fetch what the block needs but this unit is not carrying. A shed trip is
    # only worth making when there is something waiting at the other end.
    if best is None or best[0] > T_SETUP:
        if not has_goose and geese_in_shed > 0 and empty_coops:
            return _go(pos, _nearest_shed_tile(*pos), ["PICKUP", "GOOSE", 1])
        if unfed and not has_wheat and wheat_in_shed > 0 and day < SEASON_DAYS - 1:
            return _go(pos, _nearest_shed_tile(*pos),
                       ["PICKUP", "WHEAT", min(FEED_CARRY, wheat_in_shed)])

    if best is None:
        if carried > 0:
            return _go(pos, _nearest_shed_tile(*pos), ["DROP"])
        return ["PASS"]

    _tier, target, op = best
    if op == "PLACE":
        return _go(pos, target, ["PLACE", "GOOSE"])
    if op == "PLANT":
        return _go(pos, target, ["PLANT", "WHEAT"])
    return _go(pos, target, [op])


def _farmhand_op(tiles, pos, block, fallback, day, hour, carried, seeds_left):
    """One op for a unit working crops."""
    # Get produce into the shed while it can still be sold. Anything still in a
    # unit's hands when the season ends is scored as nothing, and any wave
    # bigger than the shed cap is discarded at end of day.
    last_day_flush = day >= SEASON_DAYS - 1 and hour >= 14 and carried > 0
    if carried >= DROP_THRESHOLD or last_day_flush:
        return _go(pos, _nearest_shed_tile(*pos), ["DROP"]), 0

    def classify(tile):
        got = _crop_task(tile, day)
        if got is not None and got[1] == "PLANT" and seeds_left <= 0:
            return None
        return got

    best = _best_task(tiles, block, classify, pos)
    if best is None:
        best = _best_task(tiles, fallback, classify, pos)  # its own block is idle
    if best is None:
        return ["PASS"], 0

    _tier, target, op = best
    if op == "PLANT":
        return _go(pos, target, ["PLANT", "WHEAT"]), (1 if tuple(pos) == target else 0)
    return _go(pos, target, [op]), 0


def _hire_target(full_plot, n_animal_tiles):
    """Crew size: ranchers for the animal zone, plus hands for the crops.

    Sizing the crew off tile count alone ignored that a goose needs about 3.5
    actions a day. At a large flock the ranchers ate the entire crew, nobody
    planted, and the score collapsed to a third of its value.
    """
    ranchers = (n_animal_tiles + GEESE_PER_RANCHER - 1) // GEESE_PER_RANCHER
    croppers = max(0, len(full_plot) - n_animal_tiles) // TILES_PER_UNIT
    return min(MAX_HANDS, max(1, ranchers + croppers - 1))


def _market_orders(me, private, obs, full_plot, crop_plot, n_geese, n_animal_tiles):
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

    # Geese, as many as cash allows. Payback is about three days, so this
    # outranks holding cash for anything else.
    if GOOSE_START_DAY <= day <= LAST_GOOSE_DAY:
        owned = n_geese + shed.get("GOOSE", 0)
        room = min(GOOSE_TARGET, len(full_plot)) - owned
        affordable = int(max(0, money - GOOSE_CASH_BUFFER) // GOOSE_COST)
        want = min(room, affordable, GOOSE_BUY_RATE)
        if want > 0:
            orders.append(["BUY_ANIMAL", "GOOSE", want])

    short_feed = reserve - shed.get("WHEAT", 0)
    if FEED_BUY and short_feed > 0 and day < SEASON_DAYS - 1:
        room_in_shed = SHED_CAPACITY - sum(v for v in shed.values() if v > 0)
        affordable = int(max(0, money - GOOSE_CASH_BUFFER) // 60)
        want = min(short_feed, room_in_shed, affordable)
        if want > 0:
            orders.append(["BUY_PRODUCT", "WHEAT", want])

    if day <= LAST_PLANT_DAY:
        bare = sum(1 for (x, y) in crop_plot if me["tiles"][y][x] is None)
        short = bare - seeds.get("WHEAT", 0)
        affordable = int(max(0, money - LAND_CASH_BUFFER) // WHEAT_SEED_COST)
        want = min(short, affordable)
        if want > 0:
            orders.append(["BUY_SEED", "WHEAT", want])

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
    n_geese = sum(1 for (x, y) in animal_zone
                  if isinstance(tiles[y][x], dict) and "animal" in tiles[y][x])

    # One rancher per `GEESE_PER_RANCHER` coops, but never the whole crew.
    active = sum(1 for (x, y) in animal_zone if isinstance(tiles[y][x], dict))
    n_ranchers = min(max(1, n_units - 1),
                     (active + GEESE_PER_RANCHER - 1) // GEESE_PER_RANCHER)
    if day <= LAST_GOOSE_DAY and active < len(animal_zone):
        n_ranchers = max(n_ranchers, 1)  # somebody has to build the coops

    n_crop_units = max(0, n_units - n_ranchers)
    crop_plot = full_plot[len(animal_zone):][: TILES_PER_UNIT * max(1, n_crop_units)]

    rancher_blocks = _territories(animal_zone, max(1, n_ranchers))
    crop_blocks = _territories(crop_plot, max(1, n_crop_units))

    shed = private.get("shed", {}) or {}
    geese_in_shed = shed.get("GOOSE", 0)
    wheat_in_shed = shed.get("WHEAT", 0)
    seeds_left = (private.get("seeds", {}) or {}).get("WHEAT", 0)
    inventories = private.get("inventories", []) or [{}]

    ops = []
    for i, pos in enumerate(units):
        inv = inventories[i] if i < len(inventories) and isinstance(inventories[i], dict) else {}
        carried = sum(inv.values())
        if i < n_ranchers:
            ops.append(_rancher_op(tiles, pos, rancher_blocks[i], day, inv,
                                   carried, geese_in_shed, wheat_in_shed))
        else:
            block = crop_blocks[i - n_ranchers] if n_crop_units else []
            op, used = _farmhand_op(tiles, pos, block, crop_plot, day, hour,
                                    carried, seeds_left)
            seeds_left -= used
            ops.append(op)

    market = _market_orders(me, private, obs, full_plot, crop_plot, n_geese,
                            len(animal_zone))
    return {"farmer": ops[0], "hands": ops[1:], "market": market}
