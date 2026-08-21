"""Do the strong farms adapt, or do they play the same script every game?

Our own 804 build is deterministic: across eighteen episodes its first melon
sale, peak herd, acreage and units sold are identical to within rounding, and
only the opponent's bank moves. Whether that is normal or a weakness depends
on what everyone else does.

The clean test is an opponent that appears in more than one of our replays:
same agent, two different boards, two different opponents, two different price
paths. If the acreage and timings match, they are running a fixed plan; if
they move, something is reading the game.

    py -3.12 check_adaptive.py
"""
import collections
import glob
import json
import os

ME = "Joseph Paris"
CROPS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON")
ANIMALS = ("COW", "SHEEP", "GOOSE")


def ascii_name(n):
    return (n or "?").encode("ascii", "replace").decode("ascii")


def profile(steps, seat):
    peak = collections.Counter()
    sold = collections.Counter()
    first_sale = {}
    first_plant = {}
    hands = 0
    land = {}
    for i, step in enumerate(steps):
        obs = step[0]["observation"]
        farm = obs["farms"][seat]
        day = obs["day"]
        hands = max(hands, len(farm.get("hands") or []))
        land.setdefault(len(farm.get("unlocked_quadrants", ["NW"])), day)
        if i % 24 == 0:
            c = collections.Counter()
            for row in (farm.get("tiles") or []):
                for t in row:
                    if not isinstance(t, dict):
                        continue
                    if t.get("kind") == "PLANT":
                        c[t.get("crop", "?")] += 1
                        first_plant.setdefault(t.get("crop"), day)
                    elif t.get("animal"):
                        c[t["animal"]] += 1
                        first_plant.setdefault(t["animal"], day)
            for k, v in c.items():
                peak[k] = max(peak[k], v)
        for o in ((step[seat].get("action") or {}).get("market") or []):
            if o[0] == "SELL" and len(o) > 2:
                sold[o[1]] += o[2]
                first_sale.setdefault(o[1], day)
    return {"peak": peak, "sold": sold, "first_sale": first_sale,
            "first_plant": first_plant, "hands": hands, "land": land}


def main():
    by_name = collections.defaultdict(list)
    for path in sorted(glob.glob(os.path.join("replays", "*-replay.json"))):
        try:
            with open(path) as f:
                d = json.load(f)
        except Exception:                              # noqa: BLE001
            continue
        names = [ascii_name(a.get("Name"))
                 for a in d.get("info", {}).get("Agents", [])]
        mine = 0 if names and names[0] == ME else 1
        by_name[names[1 - mine]].append((path, d, 1 - mine))

    repeats = {k: v for k, v in by_name.items() if len(v) > 1}
    if not repeats:
        print("no opponent appears twice")
        return

    for name, games in repeats.items():
        print("")
        print("=== %s, %d games" % (name, len(games)))
        profs = []
        for path, d, seat in games:
            rew = [s.get("reward") or 0 for s in d["steps"][-1]]
            p = profile(d["steps"], seat)
            profs.append(p)
            ep = os.path.basename(path).split("-")[1]
            print("  %s  bank $%-9s hands %-3d quads %d"
                  % (ep, format(int(rew[seat]), ","), p["hands"],
                     max(p["land"])))
            print("     acreage %s" % dict(
                sorted(p["peak"].items(), key=lambda kv: -kv[1])[:6]))
            print("     sold    %s" % dict(
                sorted(p["sold"].items(), key=lambda kv: -kv[1])[:6]))
            print("     first melon planted day %s, sold day %s"
                  % (p["first_plant"].get("MELON"), p["first_sale"].get("MELON")))
        # how much did the *plan* move between games?
        keys = set()
        for p in profs:
            keys |= set(p["peak"])
        print("  --- variation across games ---")
        for k in sorted(keys):
            vals = [p["peak"][k] for p in profs]
            spread = max(vals) - min(vals)
            print("     %-12s %s   spread %d" % (k, vals, spread))


if __name__ == "__main__":
    main()
