"""Sample public episodes and profile the farms that bank far above ours.

Any public episode downloads by id, not just our own -- which means the whole
competition is readable, not only the games we played. What is *not* available
is a way to look up a top player's episode ids, so this samples ids across the
range, profiles both farms, and keeps only the games where somebody banked
well beyond us.

Bank is the proxy for strength here. We do not need the exact top ten; we need
to see what a farm that banks $110k does differently from one that banks $72k,
and a sampled episode with a $108k winner answers that just as well.

Replays are ~30MB, so each is profiled and then deleted unless it clears
`--keep-above`. That is what makes sampling a hundred of them practical.

    py -3.12 scout_top.py --n 24 --keep-above 100000
"""
import argparse
import collections
import json
import os
import random
import subprocess
import sys

DIR = "scout"
SELLABLE = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG",
            "MILK", "WOOL", "FERTILIZER")


def fetch(ep):
    path = os.path.join(DIR, "episode-%d-replay.json" % ep)
    if os.path.exists(path):
        return path
    r = subprocess.run(
        [sys.executable, "-m", "kaggle", "competitions", "replay", str(ep),
         "-p", DIR], capture_output=True, text=True, timeout=900)
    return path if os.path.exists(path) else None


def profile(steps, seat):
    """What this farm grew, ran and sold."""
    sold = collections.Counter()
    peak = collections.Counter()
    hands = 0
    land_day = {}
    first_sale = {}
    for i, step in enumerate(steps):
        obs = step[0]["observation"]
        farm = obs["farms"][seat]
        day = obs["day"]
        hands = max(hands, len(farm.get("hands") or []))
        land_day.setdefault(len(farm.get("unlocked_quadrants", ["NW"])), day)
        if i % 24 == 0:
            c = collections.Counter()
            for row in (farm.get("tiles") or []):
                for t in row:
                    if not isinstance(t, dict):
                        continue
                    if t.get("kind") == "PLANT":
                        c[t.get("crop", "?")] += 1
                    elif t.get("animal"):
                        c[t["animal"]] += 1
            for k, v in c.items():
                peak[k] = max(peak[k], v)
        for o in ((step[seat].get("action") or {}).get("market") or []):
            if o[0] == "SELL" and len(o) > 2 and o[1] in SELLABLE:
                sold[o[1]] += o[2]
                first_sale.setdefault(o[1], day)
    return {"sold": sold, "peak": peak, "hands": hands,
            "land_day": land_day, "first_sale": first_sale}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--lo", type=int, default=94900000)
    ap.add_argument("--hi", type=int, default=95700000)
    ap.add_argument("--keep-above", type=int, default=100000)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    if not os.path.isdir(DIR):
        os.makedirs(DIR)
    rng = random.Random(args.seed)
    rows = []
    for _ in range(args.n):
        ep = rng.randint(args.lo, args.hi)
        path = fetch(ep)
        if not path:
            print("  %d  unavailable" % ep)
            continue
        try:
            with open(path) as f:
                d = json.load(f)
            names = [(a.get("Name") or "?").encode("ascii", "replace").decode()
                     for a in d.get("info", {}).get("Agents", [])]
            rew = [s.get("reward") or 0 for s in d["steps"][-1]]
            best = 0 if rew[0] >= rew[1] else 1
            rows.append((rew[best], ep, names[best],
                         profile(d["steps"], best)))
            print("  %d  winner %-22s $%s" % (ep, names[best][:22],
                                              format(int(rew[best]), ",")))
        except Exception as exc:                       # noqa: BLE001
            print("  %d  parse failed: %s" % (ep, exc))
        finally:
            if os.path.exists(path):
                keep = rows and rows[-1][0] >= args.keep_above \
                    and rows[-1][1] == ep
                if not keep:
                    os.remove(path)

    rows.sort(reverse=True, key=lambda r: r[0])
    print("")
    print("top farms sampled, best first")
    print("  %-9s %-11s %-6s %-5s %s" % ("bank", "winner", "hands", "quads",
                                         "sold"))
    for bank, ep, name, p in rows[:8]:
        quads = max(p["land_day"]) if p["land_day"] else 1
        top = ", ".join("%s %d" % (k, v) for k, v in
                        p["sold"].most_common(5))
        print("  $%-8s %-11s %-6d %-5d %s"
              % (format(int(bank), ","), name[:11], p["hands"], quads, top))
    if rows:
        print("")
        print("  their acreage (peak) for the best game:")
        best = rows[0]
        print("   ", dict(best[3]["peak"]))
        print("    quadrant unlocked on:", best[3]["land_day"])
        print("    first sale day:", best[3]["first_sale"])


if __name__ == "__main__":
    main()
