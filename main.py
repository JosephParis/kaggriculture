"""
Kaggriculture baseline agent: tend a plot you can actually maintain.

The naive version of this planted every tile it could reach and lost the farm.
One farmer gets 24 actions per day; watering a tile costs one action plus the
walk to it, so the sustainable plot is roughly a dozen tiles, not twenty-five.
Planting fifteen meant most went two days unwatered and turned to weeds — the
whole farm was weeds by day 6, after which the farmer stood on its one surviving
plant and worked that single tile for the remaining 24 days. Final profit: $34.

So the policy here is deliberately small. Claim a compact plot near the shed,
and never plant more than can be watered daily. Labour is the binding
constraint in this game, not land and not money.

Priority order per unit, and the reasoning:

  1. Deliver carried produce — it is worth nothing until sold, and a full
     unit cannot do anything else useful.
  2. Water anything unwatered — two missed days destroys the plant outright.
     Losing a tile costs far more than a delayed harvest.
  3. Harvest what is ready — frees the tile for replanting.
  4. Plant bare ground inside the plot.
  5. Dig weeds — recovers a tile, but nothing is dying while it waits.
"""

SHED_TILES = [(4, 4), (5, 4), (4, 5), (5, 5)]

WHEAT_FIRST_YIELD_DAY = 2
SEED_BUFFER = 6
MIN_CASH_FOR_SEED = 100

# Plot tiles, nearest-to-shed first. The NW quadrant is x,y in 0..4 and the only
# land that starts unlocked; (4,4) is left out because it is the drop point.
PLOT = [
    (3, 4), (4, 3), (3, 3), (2, 4), (4, 2), (2, 3), (3, 2), (2, 2),
    (1, 4), (4, 1), (1, 3), (3, 1),
]

# Tiles one unit can keep watered in a day, allowing for movement and the
# occasional trip to the shed. Tuned by measurement, not derived.
TILES_PER_UNIT = 6


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


def _shed_tile(tiles):
    """The drop point. Only (4,4) is unlocked at the start; the rest need land."""
    for (tx, ty) in SHED_TILES:
        if 0 <= ty < len(tiles) and 0 <= tx < len(tiles[0]) and tiles[ty][tx] != "LOCKED":
            return (tx, ty)
    return (4, 4)


def _classify(tile, day):
    """What this tile needs, or None. Lower number = more urgent."""
    if tile == "LOCKED":
        return None
    if tile is None:
        return (3, "PLANT")
    if not isinstance(tile, dict):
        return None
    kind = tile.get("kind")
    if kind == "PLANT":
        if not tile.get("watered_today"):
            return (0, "WATER")
        if day - tile.get("planted_day", day) >= WHEAT_FIRST_YIELD_DAY:
            return (1, "HARVEST")
        return None
    if kind == "WEED":
        return (4, "DIG")
    return None


def _unit_plan(tiles, x, y, carried, seeds, day, my_plot, shed):
    """Return one op for a unit that owns `my_plot`."""
    # 1. Deliver first.
    if carried > 0:
        if (x, y) == shed:
            return ["DROP"]
        return [_step_toward(x, y, shed[0], shed[1])]

    # 2-5. Find the most urgent tile in this unit's plot.
    best = None
    for (tx, ty) in my_plot:
        if not (0 <= ty < len(tiles) and 0 <= tx < len(tiles[0])):
            continue
        need = _classify(tiles[ty][tx], day)
        if need is None:
            continue
        urgency, op = need
        if op == "PLANT" and seeds.get("WHEAT", 0) <= 0:
            continue
        dist = abs(tx - x) + abs(ty - y)
        key = (urgency, dist)
        if best is None or key < best[0]:
            best = (key, (tx, ty), op)

    if best is None:
        return ["PASS"]

    _, (tx, ty), op = best
    if (x, y) == (tx, ty):
        return ["PLANT", "WHEAT"] if op == "PLANT" else [op]
    return [_step_toward(x, y, tx, ty)]


def agent(obs):
    player = obs["player"]
    me = obs["farms"][player]
    private = obs["private"]
    tiles = me["tiles"]
    day = obs["day"]
    money = me["money"]
    seeds = private.get("seeds", {}) or {}
    shed_stock = private.get("shed", {}) or {}
    inventories = private.get("inventories", []) or [{}]
    hands = me.get("hands", []) or []

    shed = _shed_tile(tiles)
    n_units = 1 + len(hands)

    # Only claim as much ground as the current workforce can water.
    plot = PLOT[: TILES_PER_UNIT * n_units]

    market = []
    have = seeds.get("WHEAT", 0)
    if have < SEED_BUFFER and money > MIN_CASH_FOR_SEED:
        market.append(["BUY_SEED", "WHEAT", SEED_BUFFER - have])
    for item, count in shed_stock.items():
        if count > 0:
            market.append(["SELL", item, count])

    # Deal out the plot so units do not converge on the same tile.
    def slice_for(i):
        return plot[i::n_units]

    fx, fy = me["farmer"]
    farmer_inv = inventories[0] if inventories else {}
    carried = sum(farmer_inv.values()) if isinstance(farmer_inv, dict) else 0
    farmer_op = _unit_plan(tiles, fx, fy, carried, seeds, day, slice_for(0), shed)

    hand_ops = []
    for i, (hx, hy) in enumerate(hands):
        inv = inventories[i + 1] if len(inventories) > i + 1 else {}
        c = sum(inv.values()) if isinstance(inv, dict) else 0
        hand_ops.append(_unit_plan(tiles, hx, hy, c, seeds, day, slice_for(i + 1), shed))

    return {"farmer": farmer_op, "hands": hand_ops, "market": market[:10]}
