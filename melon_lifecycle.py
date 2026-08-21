"""Where do the four days between a ripe melon and a sold melon go?

Our submitted builds make their first melon sale on day 14-15 while the
opponent sells on day 10-12, and melon is a race into a market that never
recovers. Melon ripens at age 10, so something between ripening and the
market is costing four days, and the carry threshold is not it.

There are only four links in that chain, and each is visible in a replay:

    planted -> ripe (age 10) -> HARVEST -> reaches the shed -> SELL

This walks a replay and dates each one, for both farms, so the slow link can
be read off rather than guessed at.

    py -3.12 melon_lifecycle.py replays/episode-XXXX-replay.json
"""
import argparse
import glob
import json
import os

ME = "Joseph Paris"
RIPE_AGE = 10


def lifecycle(steps, seat):
    planted, harvested, in_shed, sold = [], [], None, None
    carried_first = None
    prev_tiles = None
    for i, step in enumerate(steps):
        obs = step[0]["observation"]
        day = obs["day"]
        farm = obs["farms"][seat]
        tiles = farm.get("tiles") or []

        # plantings and harvests, spotted by how a tile changed
        if prev_tiles is not None:
            for y in range(len(tiles)):
                for x in range(len(tiles[y])):
                    a, b = prev_tiles[y][x], tiles[y][x]
                    a_melon = (isinstance(a, dict) and a.get("kind") == "PLANT"
                               and a.get("crop") == "MELON")
                    b_melon = (isinstance(b, dict) and b.get("kind") == "PLANT"
                               and b.get("crop") == "MELON")
                    if b_melon and not a_melon:
                        planted.append(day)
                    if a_melon and a.get("yield_units", 0) > 0 and (
                            not b_melon or b.get("yield_units", 0) <
                            a.get("yield_units", 0)):
                        harvested.append(day)
        prev_tiles = tiles

        own = step[seat].get("observation") or {}
        priv = own.get("private") or obs.get("private") or {}
        if carried_first is None:
            for inv in (priv.get("inventories") or []):
                if (inv or {}).get("MELON", 0) > 0:
                    carried_first = day
                    break
        if in_shed is None and (priv.get("shed") or {}).get("MELON", 0) > 0:
            in_shed = day
        act = step[seat].get("action") or {}
        if sold is None:
            for o in (act.get("market") or []):
                if o[0] == "SELL" and o[1] == "MELON":
                    sold = day
    return {
        "first_planted": min(planted) if planted else None,
        "n_planted": len(planted),
        "first_ripe": (min(planted) + RIPE_AGE) if planted else None,
        "first_harvest": min(harvested) if harvested else None,
        "first_carried": carried_first,
        "first_in_shed": in_shed,
        "first_sold": sold,
    }


def show(label, r):
    def d(v):
        return "day %-3s" % v if v is not None else "never  "
    print("  %-8s planted %s ripe %s harvest %s carried %s shed %s sold %s"
          % (label, d(r["first_planted"]), d(r["first_ripe"]),
             d(r["first_harvest"]), d(r["first_carried"]),
             d(r["first_in_shed"]), d(r["first_sold"])))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("replay", nargs="?")
    ap.add_argument("--dir", default="replays")
    ap.add_argument("--limit", type=int, default=4)
    args = ap.parse_args()

    paths = [args.replay] if args.replay else sorted(
        glob.glob(os.path.join(args.dir, "*-replay.json")))[:args.limit]
    for path in paths:
        with open(path) as f:
            d = json.load(f)
        names = [a.get("Name") for a in d.get("info", {}).get("Agents", [])]
        mine = 0 if names and names[0] == ME else 1
        rewards = [s.get("reward") or 0 for s in d["steps"][-1]]
        verdict = "WIN " if rewards[mine] > rewards[1 - mine] else "LOSS"
        print("")
        print("=== %s  %s  $%s vs $%s"
              % (os.path.basename(path).split("-")[1], verdict,
                 format(int(rewards[mine]), ","),
                 format(int(rewards[1 - mine]), ",")))
        show("ours", lifecycle(d["steps"], mine))
        show("theirs", lifecycle(d["steps"], 1 - mine))


if __name__ == "__main__":
    main()
