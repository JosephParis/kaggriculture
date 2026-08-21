"""Board encoding shared by training and inference.

One module, used both to build the training set from replays and to run the
policy inside the agent, because the classic way to lose a week on this is to
encode the board slightly differently in the two places and get a net that
scores well offline and plays like noise in a game.

The encoding is per-cell, which is what makes the action space tractable. A
turn commands one farmer plus up to ten hands over ~18 operations, so the
joint space is about 20^11; encoding the board once and letting each unit read
the cell it stands on turns that into eleven independent 18-way choices. This
is the shape used by the Lux AI and Halite solutions, for the same reason.

Only unit control is learned. Hiring, land, animals, seeds and market orders
stay with the heuristic: they are a handful of decisions a turn rather than a
per-cell field, they are already tuned, and leaving them alone keeps the
learned part small enough to fine-tune.

Requires numpy only, so it can ship beside `main.py` in a submission tarball.
"""
import numpy as np

CROPS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON")
ANIMALS = ("COW", "SHEEP", "GOOSE")
PRICED = ("MELON", "STRAWBERRY", "MILK", "WHEAT", "WOOL", "EGG", "FERTILIZER")

# Operations a unit can be asked for. Order is the network's output order and
# must never be reshuffled -- exported weights are indexed by it.
OPS = ("NORTH", "SOUTH", "EAST", "WEST", "PASS",
       "WATER", "HARVEST", "PLANT", "DIG",
       "FEED", "CARE", "COLLECT_FERTILIZER",
       "PICKUP", "PLACE", "DROP",
       "BUILD_COOP", "BUILD_PASTURE", "FERTILIZE")
OP_IX = {o: i for i, o in enumerate(OPS)}
N_OPS = len(OPS)

BOARD = 10
SHED = ((4, 4), (5, 4), (4, 5), (5, 5))

# Channel layout. Named so the planes stay readable when debugging a policy
# that has learned something strange.
CH = {}


def _ch(*names):
    for n in names:
        CH[n] = len(CH)


_ch("empty", "locked", "weed")
_ch(*["crop_" + c for c in CROPS])
_ch("plant_yield", "watered", "dry_days", "plant_age", "ripe")
_ch("coop", "pasture")
_ch(*["animal_" + a for a in ANIMALS])
_ch("animal_yield", "fed", "cared", "fert_ready", "animal_full")
_ch("unit_here", "shed_adj", "self_here")
_ch("their_plant", "their_animal", "their_melon", "their_ripe")
_ch("day", "hour", "money", "carrying")
_ch(*["price_" + p for p in PRICED])
N_CH = len(CH)

# Ripeness needs the crop's harvest age; duplicated from the environment.
HARVEST_AGE = {"WHEAT": 4, "CARROT": 4, "TOMATO": 8, "STRAWBERRY": 10,
               "MELON": 10}
BASE_PRICE = {"MELON": 250.0, "STRAWBERRY": 120.0, "MILK": 160.0,
              "WHEAT": 25.0, "WOOL": 200.0, "EGG": 50.0, "FERTILIZER": 100.0}


def _fill_farm(planes, farm, day, mine):
    """Write one farm's tiles into the plane stack."""
    tiles = farm.get("tiles") or []
    for y, row in enumerate(tiles):
        for x, t in enumerate(row):
            if mine:
                if t is None:
                    planes[CH["empty"], y, x] = 1.0
                    continue
                if not isinstance(t, dict):
                    planes[CH["locked"], y, x] = 1.0
                    continue
            elif not isinstance(t, dict):
                continue

            kind = t.get("kind")
            if kind == "WEED":
                if mine:
                    planes[CH["weed"], y, x] = 1.0
                continue
            if kind == "PLANT":
                crop = t.get("crop")
                age = day - t.get("planted_day", day)
                ripe = age >= HARVEST_AGE.get(crop, 99) and \
                    t.get("yield_units", 0) > 0
                if mine:
                    if crop in CROPS:
                        planes[CH["crop_" + crop], y, x] = 1.0
                    planes[CH["plant_yield"], y, x] = \
                        min(t.get("yield_units", 0), 6) / 6.0
                    planes[CH["watered"], y, x] = \
                        1.0 if t.get("watered_today") else 0.0
                    planes[CH["dry_days"], y, x] = \
                        min(t.get("consecutive_unwatered", 0), 2) / 2.0
                    planes[CH["plant_age"], y, x] = min(age, 16) / 16.0
                    planes[CH["ripe"], y, x] = 1.0 if ripe else 0.0
                else:
                    planes[CH["their_plant"], y, x] = 1.0
                    if crop == "MELON":
                        planes[CH["their_melon"], y, x] = 1.0
                    if ripe:
                        planes[CH["their_ripe"], y, x] = 1.0
                continue

            # coop or pasture
            if mine:
                planes[CH["coop" if kind == "COOP" else "pasture"], y, x] = 1.0
            animal = t.get("animal")
            if not animal:
                continue
            if mine:
                if animal in ANIMALS:
                    planes[CH["animal_" + animal], y, x] = 1.0
                held = t.get("yield_units", 0)
                planes[CH["animal_yield"], y, x] = min(held, 6) / 6.0
                planes[CH["fed"], y, x] = 1.0 if t.get("fed_today") else 0.0
                planes[CH["cared"], y, x] = 1.0 if t.get("cared_today") else 0.0
                planes[CH["fert_ready"], y, x] = \
                    1.0 if t.get("fertilizer_available") else 0.0
                planes[CH["animal_full"], y, x] = 1.0 if held >= 4 else 0.0
            else:
                planes[CH["their_animal"], y, x] = 1.0


def encode(obs, player, unit_index=None, carrying=0.0):
    """Board planes for one player.

    `unit_index` marks which unit is being asked, since every unit reads the
    same board and only differs by where it stands and what it carries. That
    one plane is what stops the policy having to be permutation-blind.
    """
    planes = np.zeros((N_CH, BOARD, BOARD), dtype=np.float32)
    farms = obs.get("farms") or []
    me = farms[player]
    _fill_farm(planes, me, obs["day"], True)
    if len(farms) > 1:
        _fill_farm(planes, farms[1 - player], obs["day"], False)

    units = [me.get("farmer")] + list(me.get("hands") or [])
    for i, pos in enumerate(units):
        if not pos:
            continue
        x, y = pos
        planes[CH["unit_here"], y, x] += 1.0
        if unit_index is not None and i == unit_index:
            planes[CH["self_here"], y, x] = 1.0
    for (x, y) in SHED:
        planes[CH["shed_adj"], y, x] = 1.0

    planes[CH["day"]] = obs["day"] / 30.0
    planes[CH["hour"]] = obs["hour"] / 24.0
    planes[CH["money"]] = min(me.get("money", 0), 60000) / 60000.0
    planes[CH["carrying"]] = min(carrying, 20) / 20.0

    prices = (obs.get("market") or {}).get("prices") or {}
    for p in PRICED:
        planes[CH["price_" + p]] = min(
            prices.get(p, BASE_PRICE[p]) / (BASE_PRICE[p] * 2.0), 2.0)
    return planes


def unit_positions(obs, player):
    farms = obs.get("farms") or []
    me = farms[player]
    return [me.get("farmer")] + list(me.get("hands") or [])
