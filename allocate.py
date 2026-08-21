"""Solve the tile allocation across every good at once, instead of one at a time.

**THIS MODEL FAILS RETRODICTION. DO NOT ALLOCATE FROM IT.** Kept for the two
parts that are validated (the drain table and the price-curve reading) and as
a record of why the approach does not work here. Scored against six
allocations whose head-to-head result is already known, it gets four of five
comparisons backwards: it ranks a build measured at 0-24 *first*, and the
current best *fifth of six*. Adding the feed cost that a twenty-goose farm
would really pay moved the numbers and not the ordering.

The reason looks structural rather than fixable by another term. Every result
that decided anything in this repo is **temporal**: bridge wheat lost because
holding melon ground under a wheat cycle pushed the premium blocks four days
late; the farm's whole season turns on the day-11 plant-out when the first
melon money lands; melon is a race where the first seller takes ~$217 and the
second takes $1. A steady-state model that multiplies units per day by a price
has no representation of any of that, so it cannot rank builds that differ in
tempo -- which is most of them.

What it did establish, and what is worth keeping:

  - The expected town drain, derived from `SHOPS` and `TOWN_CENTER_PRODUCTS`,
    reproduces the empirically measured table exactly: wheat 31/day, carrot
    and milk 19, strawberry 25, tomato/egg/wool 13, melon 1, fertilizer 0.
  - The price curves are far steeper for premium goods than the docs assume.
    Milk, strawberry and melon are at the $1 floor just **200 units above
    `MARKET_I0`**, while wheat and egg (`log`, T=400 and T=332) barely move.
    That is the real reason staples survive a contested market and premium
    goods do not, and it is why the field sells four times our wheat.
  - Actions bind before tiles do: the solver stops around 52 of 71 tiles.


Every acreage constant in `main.py` was fitted on its own, with the others held
still: melon swept to 24, strawberry to 44 (then 34), the herd to 8/4, wheat
whatever was left over. That is the wrong shape of answer. The goods compete
for the same tiles and the same actions, and each one's price falls as we
supply it, so the marginal tile of melon is only worth what it is worth *given*
how much melon we already grow -- and given how much the opponent grows.

This solves the portfolio directly. It can do that because nothing here is
unknown: `market_price`, `MARKET_PARAMS`, `MARKET_I0`, `SHOPS` and
`TOWN_CENTER_PRODUCTS` all come out of the installed environment, so the price
a unit fetches on a given day is computable rather than measurable.

Method: greedy marginal allocation. Start from an empty farm and repeatedly
hand one tile to whichever good adds the most season revenue, re-simulating
the whole market each time so that a good's price decay -- and the town drain
that offsets it -- is priced into every step. Diminishing returns fall out of
the price curve rather than being imposed, which is what makes the answer a
mix rather than a corner.

    py -3.12 allocate.py [--tiles 71] [--actions 95] [--opponent mirror]

Two budgets bind, and both matter: tiles, and the crew's productive actions
per day (issue 03 measured ~33% of ~200 unit-actions as productive).
"""
import argparse
import collections
import math

import kaggle_environments.envs.kaggriculture.kaggriculture as K

SEASON = 30
TURNS_PER_DAY = 24
TOWN_INTERVAL = 24          # town centre takes 1 of each, once a day
SHOP_INTERVAL = 4           # each shop instance consumes every 4 turns
SHOP_UNLOCK_DAYS = 3
MAX_SHOPS = 8


def expected_drain():
    """Units per day the town removes from the market, per product.

    The town centre takes one of every non-fertilizer product a day. Shops
    unlock every three days up to eight instances, drawn uniformly *with
    replacement*, and each instance consumes one of every product it demands
    every four turns -- doubled for single-product shops. Since the draw is
    uniform we can take the expectation over shop types rather than guess at
    one particular unlock sequence.
    """
    per_instance = collections.Counter()
    shops = list(K.SHOPS.items())
    for _name, wants in shops:
        rate = (TURNS_PER_DAY / SHOP_INTERVAL) * (2 if len(wants) == 1 else 1)
        for p in wants:
            per_instance[p] += rate / len(shops)

    drain = {}
    for p in K.PRODUCTS:
        base = 1.0 if p in K.TOWN_CENTER_PRODUCTS else 0.0
        drain[p] = (base, per_instance.get(p, 0.0))
    return drain


def crop_model(name):
    """Units and actions per tile per day for one crop.

    Yield follows the environment's rule: one unit at `first_yield_day`, plus
    one for every watering inside the bonus window, capped at `max_yield`.
    """
    spec = K.CROPS[name]
    if spec.get("ongoing"):
        n_yields = spec["max_yield"]
        interval = max(1, spec["interval"])
        life = spec["first_yield_day"] + n_yields * interval
        units = n_yields / float(life)
        # One plant, a survival watering every other day, one harvest per yield.
        actions = (1.0 + life * 0.5 + n_yields) / life
        return units, actions, spec["seed"] / float(life), spec["product"] if "product" in spec else name

    window_start = math.ceil(spec["max_yield_day"] / 2.0)
    waterings = max(0, spec["max_yield_day"] - window_start + 1)
    yield_units = min(spec["max_yield"], 1 + waterings)
    cycle = spec["max_yield_day"] + 1
    units = yield_units / float(cycle)
    actions = (1.0 + waterings + 1.0) / cycle
    return units, actions, spec["seed"] / float(cycle), name


def animal_model(name):
    """Units and actions per tile per day for one animal.

    CARE banks +1 a day and pays out on the next scheduled production, so an
    animal on interval `i` yields `1 + i` units every `i` days. Daily upkeep is
    feed, care and a fertilizer collection, plus a harvest every `i` days.
    """
    spec = K.ANIMALS[name]
    interval = max(1, spec["interval"])
    units = (1.0 + interval) / interval
    actions = 3.0 + 1.0 / interval
    upkeep = spec["cost"] / float(SEASON)     # amortised, plus feed below
    return units, actions, upkeep, spec["product"]


def build_goods():
    goods = {}
    for name in K.CROPS:
        u, a, cost, product = crop_model(name)
        goods[name] = {"units": u, "actions": a, "cost": cost,
                       "product": product, "kind": "crop"}
    for name in K.ANIMALS:
        u, a, cost, product = animal_model(name)
        # Animals also produce a fertilizer a day, which is a second revenue
        # stream off the same tile and the same COLLECT action.
        goods[name] = {"units": u, "actions": a, "cost": cost,
                       "product": product, "kind": "animal",
                       "fertilizer": 1.0}
    return goods


def _supply(alloc, goods, day):
    """Units each product gains from one farm on `day`."""
    out = collections.Counter()
    if day < 1:
        return out
    for name, tiles in alloc.items():
        if tiles <= 0:
            continue
        g = goods[name]
        out[g["product"]] += g["units"] * tiles
        if g["kind"] == "animal":
            out["FERTILIZER"] += g["fertilizer"] * tiles
    return out


def simulate(alloc, goods, drain, theirs=None):
    """Revenue for `alloc` against an opponent running `theirs`.

    Both farms sell into one market, so what the opponent grows sets the price
    we get -- and, just as much, what they *do not* grow leaves a market open.
    Modelling the opponent as a copy of us was wrong: it made abandoning melon
    look free, when against a melon-heavy opponent abandoning it just hands
    them the good at full price.

    Sales interleave: each day both farms' output goes to market a unit at a
    time, so neither gets to clear at the pre-glut price.
    """
    inv = {p: K.MARKET_I0 for p in K.PRODUCTS}
    params = None
    mine = 0.0
    cost = 0.0
    for day in range(SEASON):
        shops = min(MAX_SHOPS, day // SHOP_UNLOCK_DAYS)
        for p in K.PRODUCTS:
            base, per_inst = drain[p]
            inv[p] = max(0, inv[p] - (base + per_inst * shops))

        ours = _supply(alloc, goods, day)
        thrs = _supply(theirs or {}, goods, day)
        for name, tiles in alloc.items():
            if tiles > 0:
                cost += goods[name]["cost"] * tiles

        # Feed. Every animal eats a wheat a day or it escapes, and this build
        # buys rather than grows it. Leaving it out is what made a twenty-goose
        # farm look free: it is 20 wheat a day off the market, which both costs
        # us the price and pushes that price up for the next purchase.
        for who, who_alloc in ((True, alloc), (False, theirs or {})):
            eaten = sum(n for g, n in who_alloc.items()
                        if goods[g]["kind"] == "animal")
            for _ in range(int(eaten)):
                price = K.market_price("WHEAT", inv["WHEAT"], params)
                if who:
                    cost += price
                inv["WHEAT"] = max(0, inv["WHEAT"] - 1)

        for p in set(ours) | set(thrs):
            a, b = ours.get(p, 0.0), thrs.get(p, 0.0)
            n = int(max(a, b)) + 1
            for i in range(n):
                # One unit each, alternating, so both eat the same decay.
                if i < a:
                    mine += K.market_price(p, inv[p], params)
                    inv[p] += 1
                if i < b:
                    inv[p] += 1
    return mine - cost


def solve(tile_budget, action_budget, theirs, fixed=None):
    """Greedy best response to a fixed opponent allocation."""
    goods = build_goods()
    drain = expected_drain()
    alloc = collections.Counter(fixed or {})
    used_tiles = sum(alloc.values())
    used_actions = sum(goods[g]["actions"] * n for g, n in alloc.items())
    base = simulate(alloc, goods, drain, theirs)

    while used_tiles < tile_budget:
        best, best_rate = None, 0.0
        for name, g in goods.items():
            if used_actions + g["actions"] > action_budget:
                continue
            alloc[name] += 1
            rate = (simulate(alloc, goods, drain, theirs) - base) / g["actions"]
            alloc[name] -= 1
            if rate > best_rate:
                best, best_rate = name, rate
        if best is None:
            break
        alloc[best] += 1
        used_tiles += 1
        used_actions += goods[best]["actions"]
        base = simulate(alloc, goods, drain, theirs)
    return alloc, base, used_actions, []


CURRENT = {"COW": 8, "SHEEP": 4, "MELON": 24, "STRAWBERRY": 34, "WHEAT": 10}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiles", type=int, default=71,
                    help="workable tiles; 71 is three quadrants")
    ap.add_argument("--actions", type=float, default=95.0,
                    help="productive unit-actions available per day")
    ap.add_argument("--vs", default="current",
                    help="opponent: 'current' (main.py), 'none', or 'self'")
    args = ap.parse_args()

    goods = build_goods()
    drain = expected_drain()

    print("per tile per day, from the environment's own constants:")
    print("  %-11s %7s %8s %8s  %s" % ("good", "units", "actions", "seed/day",
                                       "product"))
    for name, g in sorted(goods.items(), key=lambda kv: -kv[1]["units"]):
        print("  %-11s %7.2f %8.2f %8.1f  %s"
              % (name, g["units"], g["actions"], g["cost"], g["product"]))

    print("")
    print("expected town drain per day:")
    for p in K.PRODUCTS:
        b, sh = drain[p]
        print("  %-11s %.1f/day at 8 shops" % (p, b + 8 * sh))

    theirs = None if args.vs == "none" else CURRENT
    cur = simulate(collections.Counter(CURRENT), goods, drain, theirs)
    print("")
    print("current main.py allocation, against %s: $%.0f" % (args.vs, cur))

    alloc, revenue, actions, _ = solve(args.tiles, args.actions, theirs)
    print("")
    print("best response to %s (%d tiles, %.0f actions/day):"
          % (args.vs, args.tiles, args.actions))
    for name, n in sorted(alloc.items(), key=lambda kv: -kv[1]):
        if n:
            print("  %-11s %3d tiles" % (name, n))
    print("  actions %.1f/day, modelled revenue $%.0f  (current: $%.0f, "
          "delta $%+.0f)" % (actions, revenue, cur, revenue - cur))


if __name__ == "__main__":
    main()
