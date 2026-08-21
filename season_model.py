"""A day-indexed model of a season, accurate enough to rank builds.

`allocate.py` failed because it was steady-state: it multiplied units per day
by a price and had no representation of *when* anything happened. Everything
that decides a game here is temporal -- the farm is broke until the first melon
lands on day 11 and plants out its whole board that afternoon, melon is a race
where the first seller takes ~$217 and the second takes $1, and a build that
reaches full acreage four days late loses two of strawberry's four yields.

So this tracks a bank, a planting date per tile, and an action budget, day by
day, for *both* farms against one shared market. It is still an abstraction --
there is no board, no walking, no weeds -- but the things it leaves out are
smooth, and the things it keeps are the ones that flip results.

**Verdict: calibrated, but it cannot rank. Do not allocate from it.**

It is a large improvement on `allocate.py` and still not good enough:

  - **Absolute bank is close.** Mirror $85.0k against a real $77.9k (9% high);
    solo $134k against a real $101k. The mirror number matters most and it is
    the one it gets right. Note the "$18-25k mirror" figure in STRATEGY.md is
    stale -- it describes the old goose build, and using it as a target sent
    this model off course for an hour.
  - **Ranking is a coin flip: 5/10 on `--validate`.** It thinks less melon and
    a bigger herd are improvements; both lost real head-to-heads decisively.
  - **The cause is visible in the production profile.** Strawberry 104 units
    against a measured 101, but melon **276 against a measured 187** -- 48%
    over, because the model replants melon on a clean 11-day cycle that the
    crew never actually achieves. Melon is a race whose entire value is
    timing, so over-producing it in the model makes the marginal melon look
    worthless and every "cut melon" variant look good.

Fixing that with a yield fudge factor would be fitting, not modelling, so it
was left alone. The trustworthy route is `optimize.py`, which searches the
same space against the real environment instead of a surrogate.

What survives and is worth keeping: the derived town-drain table (matches the
traced one exactly), and the reading that premium goods floor at $1 just 200
units above `MARKET_I0` while wheat and egg barely move.

    py -3.12 season_model.py --validate
"""
import argparse
import collections
import math

import kaggle_environments.envs.kaggriculture.kaggriculture as K

SEASON = 30
TURNS_PER_DAY = 24
SHOP_INTERVAL = 4
SHOP_UNLOCK_DAYS = 3
MAX_SHOPS = 8
START_MONEY = 3000
LAND_PRICES = [1000, 2000, 4000]

# Productive share of unit-actions, measured by action_stats.py: 33.4% of a
# crew's 24 actions a turn survive movement and idling.
PRODUCTIVE = 0.334


def expected_drain():
    """Units/day the town removes, per product. Derived, and it matches the
    empirically traced table exactly."""
    per_instance = collections.Counter()
    shops = list(K.SHOPS.items())
    for _name, wants in shops:
        rate = (TURNS_PER_DAY / SHOP_INTERVAL) * (2 if len(wants) == 1 else 1)
        for p in wants:
            per_instance[p] += rate / len(shops)
    return {p: (1.0 if p in K.TOWN_CENTER_PRODUCTS else 0.0,
                per_instance.get(p, 0.0)) for p in K.PRODUCTS}


def crop_spec(name):
    """Plant-to-harvest timing and yield for one crop, from the env."""
    s = K.CROPS[name]
    if s.get("ongoing"):
        interval = max(1, s["interval"])
        yields = [s["first_yield_day"] + i * interval
                  for i in range(s["max_yield"])]
        return {"seed": s["seed"], "yields": yields, "per_yield": 1,
                "life": yields[-1] + 1, "product": name, "ongoing": True}
    window = max(0, s["max_yield_day"] - math.ceil(s["max_yield_day"] / 2.0) + 1)
    units = min(s["max_yield"], 1 + window)
    return {"seed": s["seed"], "yields": [s["max_yield_day"]],
            "per_yield": units, "life": s["max_yield_day"] + 1,
            "product": name, "ongoing": False, "waterings": window}


def hire_cost(k):
    a, b, total = 1, 1, 0
    for _ in range(k):
        total += a
        a, b = b, a + b
    return total


class Farm(object):
    """One player's season: cash, plantings and the crew that tends them."""

    def __init__(self, alloc, hands=9, land=2):
        self.alloc = dict(alloc)
        self.hands = hands
        self.land_target = land
        self.money = START_MONEY
        self.land = 0
        self.plots = collections.Counter()   # crop -> tiles wanted
        self.live = []                       # [crop, planted_day]
        self.animals = collections.Counter()
        self.pending = collections.Counter(alloc)
        self.starved = 0

    def tiles_available(self, day):
        """Workable tiles: NW free, each purchase adds 25, minus animal tiles."""
        return 25 * (1 + self.land) - sum(self.animals.values())

    def crew(self):
        """Hands hired, by the same rule `main.py` uses.

        Fixing this at a constant was wrong and it showed: a build with more
        melon simply blew the action budget and lost tiles, when the real
        agent would have hired the hands to work them. Crew scales with the
        board, so acreage and labour move together.
        """
        animals = sum(self.animals.values()) or sum(
            self.alloc.get(k, 0) for k in K.ANIMALS)
        ranchers = (animals + 4) // 5
        croppers = max(0, 25 * (1 + self.land) - animals) // 8
        return min(10, max(1, ranchers + croppers - 1))

    def action_budget(self):
        return (1 + self.crew()) * TURNS_PER_DAY * PRODUCTIVE

    def upkeep_actions(self, day):
        need = 3.5 * sum(self.animals.values())
        for crop, planted in self.live:
            spec = crop_spec(crop)
            age = day - planted
            if spec["ongoing"]:
                need += 0.5
            elif age <= spec["yields"][0]:
                need += spec["waterings"] / float(spec["life"]) + 0.4
        return need


def simulate(alloc_a, alloc_b, hands_a=9, hands_b=9, land_a=2, land_b=2):
    """Run both farms against one market. Returns (bank_a, bank_b)."""
    drain = expected_drain()
    inv = {p: K.MARKET_I0 for p in K.PRODUCTS}
    farms = [Farm(alloc_a, hands_a, land_a), Farm(alloc_b, hands_b, land_b)]

    for day in range(SEASON):
        shops = min(MAX_SHOPS, day // SHOP_UNLOCK_DAYS)
        for p in K.PRODUCTS:
            base, per = drain[p]
            inv[p] = max(0, inv[p] - (base + per * shops))

        harvest = [collections.Counter(), collections.Counter()]

        for idx, f in enumerate(farms):
            # --- crew ---------------------------------------------------
            f.money -= hire_cost(f.crew())

            # --- land ---------------------------------------------------
            if f.land < f.land_target and f.money >= LAND_PRICES[f.land] + 300:
                f.money -= LAND_PRICES[f.land]
                f.land += 1

            # --- animals: bought as cash allows, from day 3 -------------
            if day >= 3:
                for kind in ("SHEEP", "COW", "GOOSE"):
                    want = f.alloc.get(kind, 0) - f.animals[kind]
                    while want > 0 and f.money >= K.ANIMALS[kind]["cost"] + 700:
                        f.money -= K.ANIMALS[kind]["cost"]
                        f.animals[kind] += 1
                        f.pending[kind] -= 1
                        want -= 1

            # --- feed ---------------------------------------------------
            n_animals = sum(f.animals.values())
            for _ in range(n_animals):
                price = K.market_price("WHEAT", inv["WHEAT"])
                if f.money < price:
                    f.starved += 1
                    break
                f.money -= price
                inv["WHEAT"] = max(0, inv["WHEAT"] - 1)

            # --- planting: cash-gated, which is the whole early game ----
            room = f.tiles_available(day) - len(f.live)
            for crop in ("MELON", "STRAWBERRY", "WHEAT", "CARROT", "TOMATO"):
                want = f.alloc.get(crop, 0)
                if not want:
                    continue
                have = sum(1 for c, _ in f.live if c == crop)
                spec = crop_spec(crop)
                last = SEASON - 1 - spec["yields"][-1]
                while (have < want and room > 0 and day <= last
                       and f.money >= spec["seed"] + 300):
                    f.money -= spec["seed"]
                    f.live.append([crop, day])
                    have += 1
                    room -= 1

            # --- tending: if the crew is short, tiles die ---------------
            budget, need = f.action_budget(), f.upkeep_actions(day)
            if need > budget and f.live:
                # Drop the tiles the crew cannot keep alive.
                over = int(math.ceil((need - budget) / 1.0))
                f.live = f.live[:max(0, len(f.live) - over)]

            # --- production --------------------------------------------
            for kind, n in f.animals.items():
                spec = K.ANIMALS[kind]
                if not n:
                    continue
                interval = max(1, spec["interval"])
                if day >= 3 + spec["first_yield_day"]:
                    harvest[idx][spec["product"]] += n * (1.0 + interval) / interval
                # Fertilizer starts the day after placement, before the first
                # milk or egg does, and accrues whether or not the animal ate.
                harvest[idx]["FERTILIZER"] += n

            keep = []
            for entry in f.live:
                crop, planted = entry
                spec = crop_spec(crop)
                age = day - planted
                if age in spec["yields"]:
                    harvest[idx][spec["product"]] += spec["per_yield"]
                if age < spec["life"]:
                    keep.append(entry)
                elif not spec["ongoing"]:
                    pass          # one-time crops free the tile for replanting
            f.live = keep

        # --- sell: both farms into one market, interleaved --------------
        for p in set(harvest[0]) | set(harvest[1]):
            a, b = harvest[0].get(p, 0.0), harvest[1].get(p, 0.0)
            for i in range(int(max(a, b)) + 1):
                if i < a:
                    farms[0].money += K.market_price(p, inv[p])
                    inv[p] += 1
                if i < b:
                    farms[1].money += K.market_price(p, inv[p])
                    inv[p] += 1

    return farms[0].money, farms[1].money


TILES = 71          # three quadrants, which is what MAX_LAND=2 buys


def build(cow=8, sheep=4, goose=0, melon=24, straw=34):
    """An allocation in the shape the agent actually produces.

    `crop_of` zones the animal block, then melon, then strawberry, and gives
    **everything left over to wheat**. So cutting melon does not leave bare
    ground, it grows wheat -- and a validation set that forgets that is
    testing a farm the agent would never run. This is what made the model look
    like it preferred less melon: the comparison was against idle tiles.
    """
    animals = cow + sheep + goose
    used = animals + melon + straw
    alloc = {"COW": cow, "SHEEP": sheep, "GOOSE": goose,
             "MELON": melon, "STRAWBERRY": straw,
             "WHEAT": max(0, TILES - used)}
    return {k: v for k, v in alloc.items() if v}


CURRENT = build()
STARTER = {"WHEAT": 1}

# Every row lost to the incumbent in a real head-to-head, recorded in TRIED.md.
KNOWN = [
    ("melon 8",            build(melon=8),                False),
    ("melon 16",           build(melon=16),               False),
    ("melon 36",           build(melon=36),               False),
    ("strawberry 8",       build(straw=8),                False),
    ("strawberry 44",      build(straw=44),               False),
    ("herd 6/6",           build(cow=6, sheep=6),         False),
    ("herd 12/4",          build(cow=12, sheep=4),        False),
    ("herd 10/4",          build(cow=10, sheep=4),        False),
    ("geese for herd",     build(cow=0, sheep=0, goose=12), False),
    ("portfolio 12 geese", build(cow=3, sheep=2, goose=12,
                                 melon=6, straw=13),      False),
    # The one change that beat the incumbent: strawberry 44 -> 34, which is
    # exactly "give wheat a block of its own". 21-3.
    ("wheat block (34)",   build(straw=34),               None),
]


def validate():
    """Score the model against results we already know. It must rank the
    incumbent above every build that lost to it head to head."""
    ours, _ = simulate(CURRENT, CURRENT)
    solo, _ = simulate(CURRENT, STARTER)
    print("calibration")
    print("  current vs starter : $%8.0f   (real: $101,400)" % solo)
    print("  current vs itself  : $%8.0f   (real: $ 77,900)" % ours)

    print("")
    print("retrodiction -- every row lost to the incumbent in a real h2h")
    passed = 0
    scored = 0
    for name, alloc, should_beat in KNOWN:
        mine, theirs = simulate(alloc, CURRENT)
        model_says = mine > theirs
        if should_beat is None:
            print("  %-20s model $%8.0f vs $%8.0f  %s   (known 21-3 WIN)"
                  % (name, mine, theirs,
                     "beats" if model_says else "loses "))
            continue
        scored += 1
        ok = (model_says == should_beat)
        passed += ok
        print("  %-20s model $%8.0f vs $%8.0f  %s   %s"
              % (name, mine, theirs,
                 "beats" if model_says else "loses ",
                 "OK" if ok else "WRONG"))
    print("")
    print("  %d/%d correct" % (passed, scored))
    return passed, scored


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    args = ap.parse_args()
    validate()


if __name__ == "__main__":
    main()
