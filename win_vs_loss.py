"""Same build, different outcome: what actually varies?

Comparing our build against a better one confounds two things -- how the
builds differ, and how the games differed. Comparing one build's wins against
its own losses removes the first, so whatever separates them is situational:
the opponent, the melon race, the board.

Reads the summary written by `scan_episodes.py` so it knows each episode's
verdict, then measures both farms in each.

    py -3.12 win_vs_loss.py --summary replays/summary_55637915.csv
"""
import argparse
import collections
import csv
import glob
import json
import os

ME = "Joseph Paris"
SELLABLE = {"WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG",
            "MILK", "WOOL", "FERTILIZER"}


def measure(steps, seat):
    sold = collections.Counter()
    first_melon = None
    peak = collections.Counter()
    hands = 0
    for step in steps:
        obs = step[0]["observation"]
        farm = obs["farms"][seat]
        hands = max(hands, len(farm.get("hands") or []))
        for row in (farm.get("tiles") or []):
            for t in row:
                if isinstance(t, dict) and t.get("animal"):
                    peak["_herd_now"] += 0
        act = step[seat].get("action") or {}
        for o in (act.get("market") or []):
            if o[0] == "SELL" and len(o) > 2 and o[1] in SELLABLE:
                sold[o[1]] += o[2]
                if o[1] == "MELON" and first_melon is None:
                    first_melon = obs["day"]
    # herd peak, measured once at the end of each day rather than per turn
    herd = 0
    for step in steps[::24]:
        farm = step[0]["observation"]["farms"][seat]
        herd = max(herd, sum(1 for r in farm.get("tiles") or []
                             for t in r
                             if isinstance(t, dict) and t.get("animal")))
    return {"sold": sold, "first_melon": first_melon, "herd": herd,
            "hands": hands}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", required=True)
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.summary)))
    groups = {"WIN": [], "LOSS": []}
    opp = {"WIN": [], "LOSS": []}

    for row in rows:
        path = "replays/episode-%s-replay.json" % row["episode"]
        if not os.path.exists(path):
            continue
        with open(path) as f:
            d = json.load(f)
        names = [a.get("Name") for a in d.get("info", {}).get("Agents", [])]
        mine = 0 if names and names[0] == ME else 1
        v = row["verdict"]
        if v not in groups:
            continue
        groups[v].append(measure(d["steps"], mine))
        opp[v].append((float(row["them"]), names[1 - mine]))

    def avg(rs, key, sub=None):
        vals = [(r["sold"][sub] if sub else r[key]) for r in rs
                if (r[key] is not None or sub)]
        vals = [v for v in vals if v is not None]
        return sum(vals) / float(len(vals)) if vals else 0.0

    print("%d wins, %d losses" % (len(groups["WIN"]), len(groups["LOSS"])))
    print("")
    print("  %-22s %10s %10s %10s" % ("", "in wins", "in losses", "delta"))
    print("  %-22s %10.0f %10.0f %+10.0f"
          % ("opponent final bank",
             sum(x for x, _ in opp["WIN"]) / max(1, len(opp["WIN"])),
             sum(x for x, _ in opp["LOSS"]) / max(1, len(opp["LOSS"])),
             sum(x for x, _ in opp["LOSS"]) / max(1, len(opp["LOSS"]))
             - sum(x for x, _ in opp["WIN"]) / max(1, len(opp["WIN"]))))
    for label, key, sub in (("our first melon sale", "first_melon", None),
                            ("our peak herd", "herd", None),
                            ("our max hands", "hands", None)):
        w, l = avg(groups["WIN"], key), avg(groups["LOSS"], key)
        print("  %-22s %10.1f %10.1f %+10.1f" % (label, w, l, l - w))
    for item in ("MELON", "MILK", "WHEAT", "STRAWBERRY", "FERTILIZER",
                 "WOOL"):
        w = avg(groups["WIN"], "sold", item)
        l = avg(groups["LOSS"], "sold", item)
        print("  %-22s %10.0f %10.0f %+10.0f" % ("we sold " + item, w, l,
                                                 l - w))
    print("")
    print("  opponents beaten : %s"
          % ", ".join(sorted({n for _, n in opp["WIN"]})[:6]))
    print("  opponents lost to: %s"
          % ", ".join(sorted({n for _, n in opp["LOSS"]})[:6]))


if __name__ == "__main__":
    main()
