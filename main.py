"""
Kaggriculture agent: buy labour, buy land, work every tile you can reach.

The single-farmer baseline scored ~$6,000. Three things were leaving an order of
magnitude on the table:

  1. **Labour is nearly free.** A hire costs `fib(n)` for the n-th hire of the
     day and resets every morning, so eight hands cost $54/day for 192 extra
     actions -- $0.28 an action against roughly $11 of return.
  2. **Nobody needs to walk to the shed to store things.** `_end_of_day` drops
     every unit's inventory into the shed automatically. Units stay in the
     field; they only make a shed trip when the 100-item shed cap is the
     binding constraint (see DROP below).
  3. **Watering every day is a waste.** A plant dies only after *two*
     consecutive dry days, and watering only adds yield inside the bonus
     window. Wheat therefore wants watering on days 0, 2, 3, 4 -- not day 1 --
     which is four actions for the same 4 units instead of five.

Hands and land buy each other: hands are worthless without tiles to work, and
tiles are worthless without hands to water them, so the two scale together.

Units hold a **fixed territory** for the day rather than chasing whatever tile
is most urgent globally. Re-deciding every turn made units oscillate between
two tiles and walk more than they worked; the farm filled with weeds because
plants went dry while their keeper was in transit.

Everything is greedy and per-turn. `actTimeout` is 1 second across 720 turns,
so there is no room for search.

Policy constants can be overridden by `KAG_*` environment variables so a sweep
can tune them without editing this file. Defaults are what gets submitted.

See docs/STRATEGY.md for the economics behind the numbers.
"""
import os

BOARD = 10
SHED_ACCESS = [(4, 4), (5, 4), (4, 5), (5, 5)]

# Copied from the environment source. A submitted agent cannot import
# kaggle_environments, so these are duplicated rather than referenced.
WHEAT_SEED_COST = 10
WHEAT_MAX_YIELD_DAY = 4
WHEAT_WINDOW_START = (WHEAT_MAX_YIELD_DAY + 1) // 2  # 2
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

# Keep enough back that buying land never leaves us unable to buy seed.
LAND_CASH_BUFFER = _P("LAND_CASH_BUFFER", 300)

# How many quadrants to buy. Land comes straight off the final score, and the
# third quadrant costs $4,000 -- swept at $12,502 for two against $9,405 for
# three, so it never earns that back in the days it has left.
MAX_LAND = _P("MAX_LAND", 2)

# Carry this much before making a shed trip. Harvests arrive in waves, and a
# wave larger than the 100-item shed cap is silently discarded at end of day.
DROP_THRESHOLD = _P("DROP_THRESHOLD", 14)

# Wheat planted later than this cannot reach max_yield_day before the season
# ends, so the tile is better left empty.
LAST_PLANT_DAY = SEASON_DAYS - 1 - WHEAT_MAX_YIELD_DAY

# Tier ordering for tasks. Lower is more urgent.
T_RESCUE = 0   # dies tonight if untouched
T_DROP = 1     # carrying enough that the shed cap is at risk
T_HARVEST = 2
T_WATER = 3    # yield bonus only; the plant is in no danger
T_PLANT = 4
T_DIG = 5


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


def _workable_tiles(tiles):
    """Unlocked tiles we are willing to farm, nearest the shed first.

    The four shed-access tiles stay clear: they are the only squares from which
    PICKUP and DROP work, which matters as soon as there are animals to feed.
    """
    out = []
    for y, row in enumerate(tiles):
        for x, tile in enumerate(row):
            if tile == "LOCKED" or (x, y) in SHED_ACCESS:
                continue
            out.append((abs(x - 4.5) + abs(y - 4.5), x, y))
    out.sort()
    return [(x, y) for _, x, y in out]


def _territories(plot, n_units):
    """Split the plot into `n_units` contiguous, spatially local blocks.

    Sorting by quadrant before distance keeps each block in one corner of the
    board, so a unit walks between neighbouring tiles instead of across the
    farm. Interleaving the plot instead (`plot[i::n]`) scatters each unit's
    tiles over the whole board and burns the day on movement.
    """
    ordered = sorted(plot, key=lambda t: (_quadrant_rank(*t),
                                          abs(t[0] - 4.5) + abs(t[1] - 4.5)))
    blocks = [[] for _ in range(n_units)]
    if not ordered:
        return blocks
    per = max(1, (len(ordered) + n_units - 1) // n_units)
    for i, tile in enumerate(ordered):
        blocks[min(n_units - 1, i // per)].append(tile)
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


def _classify(tile, day):
    """What this tile needs, or None."""
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
            tier = T_RESCUE if tile.get("consecutive_unwatered", 0) >= 1 else T_WATER
            return (tier, "WATER")
        return None
    if kind == "WEED":
        return (T_DIG, "DIG")
    return None


def _nearest_shed_tile(x, y):
    return min(SHED_ACCESS, key=lambda t: abs(t[0] - x) + abs(t[1] - y))


def _unit_op(tiles, pos, block, fallback, day, hour, carried, seeds_left):
    """One op for one unit, choosing from its own block before the shared pool."""
    x, y = pos

    # Get produce into the shed while it can still be sold. Anything still in a
    # unit's hands at the end of the last day is dropped after scoring, and any
    # wave bigger than the shed cap is discarded, so both cases want a trip.
    last_day_flush = day >= SEASON_DAYS - 1 and hour >= 14 and carried > 0
    if carried >= DROP_THRESHOLD or last_day_flush:
        sx, sy = _nearest_shed_tile(x, y)
        return (["DROP"] if (x, y) == (sx, sy) else [_step_toward(x, y, sx, sy)]), 0

    best = None
    for source in (block, fallback):
        for (tx, ty) in source:
            need = _classify(tiles[ty][tx], day)
            if need is None:
                continue
            tier, op = need
            if op == "PLANT" and seeds_left <= 0:
                continue
            key = (tier, abs(tx - x) + abs(ty - y))
            if best is None or key < best[0]:
                best = (key, (tx, ty), op)
        if best is not None:
            break  # its own block had work; do not wander

    if best is None:
        return ["PASS"], 0

    _, (tx, ty), op = best
    if (x, y) != (tx, ty):
        return [_step_toward(x, y, tx, ty)], 0
    if op == "PLANT":
        return ["PLANT", "WHEAT"], 1
    return [op], 0


def _market_orders(me, private, obs, full_plot, plot):
    """Hire, expand, sell everything, keep seed stocked -- in that order.

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

    # Hire at the top of the day, before there is work to fall behind on. Hands
    # last one day, so this repeats every morning.
    if hour <= 1 and day <= SEASON_DAYS - 2:
        want = min(MAX_HANDS, max(1, len(full_plot) // TILES_PER_UNIT - 1))
        for _ in range(max(0, want - me.get("hires_today", 0))):
            orders.append(["HIRE"])

    # Land, as early as it clears. Twenty-five more tiles pay for themselves in
    # about two days of the labour they unlock.
    bought = len(me.get("unlocked_quadrants", ["NW"])) - 1
    if bought < min(MAX_LAND, len(LAND_PRICES)) and day <= SEASON_DAYS - 8:
        price = LAND_PRICES[bought]
        if money >= price + LAND_CASH_BUFFER:
            orders.append(["BUY_LAND"])

    # Sell the shed out every turn. Wheat is a `log` sink -- it holds ~$20 at
    # any volume we can reach -- so there is nothing to gain by holding, and
    # the shed's 100-item cap silently discards the overflow if we do.
    for item, count in shed.items():
        if count > 0:
            orders.append(["SELL", item, count])

    # Enough seed to plant every bare tile in the plot.
    if day <= LAST_PLANT_DAY:
        bare = sum(1 for (x, y) in plot if me["tiles"][y][x] is None)
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
    n_units = 1 + len(hands)

    # Claim only as much ground as the current crew can keep alive. The plot
    # grows as hands are hired and as quadrants are unlocked.
    full_plot = _workable_tiles(tiles)
    plot = full_plot[: TILES_PER_UNIT * n_units]
    blocks = _territories(plot, n_units)

    seeds = private.get("seeds", {}) or {}
    seeds_left = seeds.get("WHEAT", 0)

    inventories = private.get("inventories", []) or [{}]
    units = [tuple(me["farmer"])] + [tuple(p) for p in hands]

    ops = []
    for i, pos in enumerate(units):
        inv = inventories[i] if i < len(inventories) else {}
        carried = sum(inv.values()) if isinstance(inv, dict) else 0
        op, used = _unit_op(tiles, pos, blocks[i], plot, day, hour, carried, seeds_left)
        seeds_left -= used
        ops.append(op)

    market = _market_orders(me, private, obs, full_plot, plot)
    return {"farmer": ops[0], "hands": ops[1:], "market": market}
