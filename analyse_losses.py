"""Diff our farm against the farm that beat us, across downloaded loss replays.

TRIED.md has had "replay analysis of a loss to a strong opponent" as its
number one open lead since 18 August, on the grounds that everything else says
the remaining gap is execution and this is the only way to see it directly.

Replays carry both farms in full -- `obs["farms"]` is public -- plus both
players' action dicts, so nothing here is inferred.

    py -3.12 analyse_losses.py [--dir replays]

Reports, for us and for the winner, the things the backlog argues about:
land bought, crew size, herd size and composition, crop acreage, and the
opening tempo.
"""
import argparse
import collections
import glob
import json
import os

ANIMALS = ("COW", "SHEEP", "GOOSE")


def census(farm):
    """Tile counts by what is standing on them."""
    got = collections.Counter()
    for row in farm["tiles"]:
        for t in row:
            if not isinstance(t, dict):
                continue
            kind = t.get("kind")
            if kind == "PLANT":
                got[t.get("crop", "?")] += 1
            elif kind in ("COOP", "PASTURE"):
                if t.get("animal"):
                    got[t["animal"]] += 1
                else:
                    got["empty_" + kind] += 1
            elif kind == "WEED":
                got["WEED"] += 1
    return got


def profile(steps, seat):
    """Per-day snapshot of one farm, plus its market activity."""
    days = {}
    orders = collections.Counter()
    sells = collections.Counter()
    peak_hands = collections.Counter()
    for i, step in enumerate(steps):
        obs = step[0]["observation"]
        day, hour = obs["day"], obs["hour"]
        farm = obs["farms"][seat]
        peak_hands[day] = max(peak_hands[day], len(farm["hands"]))
        act = step[seat].get("action") or {}
        for o in (act.get("market") or []):
            orders[o[0]] += 1
            if o[0] == "SELL" and len(o) > 2:
                sells[o[1]] += o[2]
        if hour == 12:
            days[day] = {
                "money": farm["money"],
                "quads": len(farm.get("unlocked_quadrants", ["NW"])),
                "census": census(farm),
            }
    return days, orders, sells, peak_hands


def first_day(days, key, pred):
    for d in sorted(days):
        if pred(days[d][key]):
            return d
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="replays")
    args = ap.parse_args()

    agg = {"me": collections.Counter(), "them": collections.Counter()}
    n = 0
    for path in sorted(glob.glob(os.path.join(args.dir, "*-replay.json"))):
        with open(path) as f:
            d = json.load(f)
        names = [a.get("Name") for a in d.get("info", {}).get("Agents", [])]
        steps = d["steps"]
        final = steps[-1]
        rewards = [s.get("reward") or 0 for s in final]
        mine = 0 if names and names[0] == "Joseph Paris" else 1
        them = 1 - mine
        if rewards[mine] >= rewards[them]:
            continue                      # only the losses are kept on disk
        n += 1
        print("\n=== %s   us %,.0f  vs  %s %,.0f".replace(",", "")
              % (os.path.basename(path).split("-")[1], rewards[mine],
                 names[them], rewards[them]))

        for label, seat in (("us", mine), ("them", them)):
            days, orders, sells, hands = profile(steps, seat)
            last = days[max(days)]
            herd = sum(last["census"][a] for a in ANIMALS)
            crops = {k: v for k, v in last["census"].items()
                     if k not in ANIMALS and not k.startswith("empty_")
                     and k != "WEED"}
            peak_herd = max(
                sum(days[d]["census"][a] for a in ANIMALS) for d in days)
            land_day = first_day(days, "quads", lambda q: q >= 3)
            print("  %-5s hands %2d/%2d(max)  quads %d (3rd on day %s)  "
                  "herd %d (peak %d)  crops %s"
                  % (label, hands[max(hands)], max(hands.values()),
                     last["quads"], land_day, herd, peak_herd,
                     dict(sorted(crops.items(), key=lambda kv: -kv[1]))))
            print("        sold %s" % dict(
                sorted(sells.items(), key=lambda kv: -kv[1])))
            key = "me" if label == "us" else "them"
            agg[key]["hands"] += max(hands.values())
            agg[key]["quads"] += last["quads"]
            agg[key]["herd"] += peak_herd
            for c, v in crops.items():
                agg[key]["crop_" + c] += v

    if not n:
        print("no loss replays found in %s" % args.dir)
        return
    print("\n=== averages over %d losses ===" % n)
    keys = sorted(set(agg["me"]) | set(agg["them"]))
    print("  %-16s %8s %8s" % ("", "us", "winner"))
    for k in keys:
        print("  %-16s %8.1f %8.1f"
              % (k, agg["me"][k] / float(n), agg["them"][k] / float(n)))


if __name__ == "__main__":
    main()
