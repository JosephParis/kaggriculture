"""What the crew actually does on days 0-5.

Three fixes to the herd-first opening were proposed off a money trace and all
three failed, which says the money trace was the wrong layer. The bank shows
that $2,700 leaves on day 0 and nothing comes back for twelve days; it does
not show whether the crew is idle, walking, or working on the wrong things.

This tallies unit-actions per day for the opening, alongside what the board
looks like, so the two builds can be read against each other.

    py -3.12 trace_opening.py --knobs HERD_FIRST=1,... --days 6
"""
import argparse
import collections
import os
import subprocess
import sys

PROBE = r'''
import collections, json, os, main
from kaggle_environments import make

MOVES = {"NORTH", "SOUTH", "EAST", "WEST"}
per_day = collections.defaultdict(collections.Counter)
board = {}

def traced(obs):
    d = obs["day"]
    out = main.agent(obs)
    me = obs["farms"][obs["player"]]
    ops = [out["farmer"]] + list(out["hands"])
    for op in ops:
        per_day[d][op[0]] += 1
    per_day[d]["_units"] = max(per_day[d]["_units"], len(ops))
    if d not in board:
        tiles = me["tiles"]
        priv = obs.get("private") or {}
        board[d] = {
            "money": me["money"],
            "animals": sum(1 for r in tiles for t in r
                           if isinstance(t, dict) and t.get("animal")),
            "structs": sum(1 for r in tiles for t in r
                           if isinstance(t, dict)
                           and t.get("kind") in ("COOP", "PASTURE")),
            "plants": sum(1 for r in tiles for t in r
                          if isinstance(t, dict) and t.get("kind") == "PLANT"),
            "shed_animals": sum(v for k, v in (priv.get("shed") or {}).items()
                                if k in ("COW", "SHEEP", "GOOSE")),
            "seeds": sum((priv.get("seeds") or {}).values()),
        }
    return out

env = make("kaggriculture", configuration={"seed": int(os.environ["TSEED"])},
           debug=False)
env.run([traced, "starter"])
days = int(os.environ["TDAYS"])
rows = []
for d in range(days):
    c = per_day.get(d, collections.Counter())
    tot = sum(v for k, v in c.items() if not k.startswith("_"))
    rows.append({
        "day": d, "units": c.get("_units", 0), "total": tot,
        "move": sum(c[m] for m in MOVES), "pass": c.get("PASS", 0),
        "plant": c.get("PLANT", 0), "water": c.get("WATER", 0),
        "build": c.get("BUILD_PASTURE", 0) + c.get("BUILD_COOP", 0),
        "place": c.get("PLACE", 0), "pickup": c.get("PICKUP", 0),
        "other": tot - sum(c[m] for m in MOVES) - c.get("PASS", 0)
                 - c.get("PLANT", 0) - c.get("WATER", 0)
                 - c.get("BUILD_PASTURE", 0) - c.get("BUILD_COOP", 0)
                 - c.get("PLACE", 0) - c.get("PICKUP", 0),
        "board": board.get(d, {}),
    })
print(json.dumps({"rows": rows, "bank": float(env.steps[-1][0].reward or 0)}))
'''


def run(knobs, seed, days):
    env = dict(os.environ)
    env.update({"PYTHONPATH": ".", "TSEED": str(seed), "TDAYS": str(days),
                "OMP_NUM_THREADS": "1"})
    for pair in (knobs or "").split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            env["KAG_" + k.strip()] = v.strip()
    out = subprocess.run([sys.executable, "-c", PROBE], env=env,
                         capture_output=True, text=True, timeout=3600).stdout
    import json
    for line in reversed(out.strip().splitlines()):
        if line.startswith("{"):
            return json.loads(line)
    return None


def show(label, got):
    print("")
    print("%s   final bank $%s" % (label, format(int(got["bank"]), ",")))
    print("  %3s %5s %6s %6s %6s %6s %6s %6s %6s | %6s %7s %7s %6s"
          % ("day", "units", "acts", "move", "idle", "plant", "water",
             "build", "place", "money", "animals", "structs", "plants"))
    for r in got["rows"]:
        b = r["board"]
        print("  %3d %5d %6d %6d %6d %6d %6d %6d %6d | %6d %7d %7d %6d"
              % (r["day"], r["units"], r["total"], r["move"], r["pass"],
                 r["plant"], r["water"], r["build"], r["place"],
                 b.get("money", 0), b.get("animals", 0), b.get("structs", 0),
                 b.get("plants", 0)))


def main_cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--knobs", default="")
    ap.add_argument("--label", default="build")
    ap.add_argument("--seed", type=int, default=3000)
    ap.add_argument("--days", type=int, default=6)
    ap.add_argument("--compare", action="store_true",
                    help="also trace the incumbent, for reading side by side")
    args = ap.parse_args()

    if args.compare:
        base = run("", args.seed, args.days)
        if base:
            show("incumbent", base)
    got = run(args.knobs, args.seed, args.days)
    if got:
        show(args.label, got)


if __name__ == "__main__":
    main_cli()
