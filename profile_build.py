"""Read a build's configuration back out of what it did.

The ladder submissions have diverged from this repo: twelve exist, the 18
August builds rate 581-628, and a 19-20 August lineage rates 752-804 using an
opening this repo has never had. There is no API for downloading your own
submitted agent, but a replay carries every observation and every action, so
the *configuration* can be recovered from behaviour -- herd size and mix, crop
acreage, crew curve, when land was bought, when melon went in.

    py -3.12 profile_build.py --replays replays          # submitted builds
    py -3.12 profile_build.py --agent main.py            # this repo, for diff

Both modes print the same fields, so they can be compared line for line.
"""
import argparse
import collections
import glob
import json
import os

ANIMALS = ("COW", "SHEEP", "GOOSE")
ME = "Joseph Paris"


def census(farm):
    got = collections.Counter()
    for row in farm["tiles"]:
        for t in row:
            if not isinstance(t, dict):
                continue
            if t.get("kind") == "PLANT":
                got[t.get("crop", "?")] += 1
            elif t.get("animal"):
                got[t["animal"]] += 1
    return got


def profile_steps(steps, seat):
    """Peak acreage, herd, crew and timings for one farm."""
    peak = collections.Counter()
    hands_by_day = collections.Counter()
    land_days = {}
    first_plant = {}
    sold = collections.Counter()
    for step in steps:
        obs = step[0]["observation"]
        day = obs["day"]
        farm = obs["farms"][seat]
        hands_by_day[day] = max(hands_by_day[day], len(farm["hands"]))
        quads = len(farm.get("unlocked_quadrants", ["NW"]))
        land_days.setdefault(quads, day)
        c = census(farm)
        for k, v in c.items():
            peak[k] = max(peak[k], v)
            if v and k not in first_plant:
                first_plant[k] = day
        act = step[seat].get("action") or {}
        for o in (act.get("market") or []):
            if o[0] == "SELL" and len(o) > 2:
                sold[o[1]] += o[2]
    return peak, hands_by_day, land_days, first_plant, sold


def show(label, peak, hands, land_days, first_plant, sold):
    herd = {a: peak[a] for a in ANIMALS if peak[a]}
    crops = {k: v for k, v in peak.items() if k not in ANIMALS}
    print("  %-22s %s" % ("herd (peak)", herd or "-"))
    print("  %-22s %s" % ("crop acreage (peak)",
                          dict(sorted(crops.items(), key=lambda kv: -kv[1]))))
    early = [hands.get(d, 0) for d in range(0, 12)]
    print("  %-22s day0-11 %s   max %d"
          % ("hands", early, max(hands.values()) if hands else 0))
    print("  %-22s %s" % ("quadrant unlocked on",
                          {k: v for k, v in sorted(land_days.items())}))
    print("  %-22s %s" % ("first seen on a tile",
                          dict(sorted(first_plant.items(),
                                      key=lambda kv: kv[1]))))
    print("  %-22s %s" % ("units sold",
                          dict(sorted(sold.items(), key=lambda kv: -kv[1]))))


def from_replays(pattern):
    paths = sorted(glob.glob(os.path.join(pattern, "*-replay.json")))
    if not paths:
        print("no replays in %s" % pattern)
        return
    for path in paths:
        with open(path) as f:
            d = json.load(f)
        names = [a.get("Name") for a in d.get("info", {}).get("Agents", [])]
        seat = 0 if names and names[0] == ME else 1
        rewards = [s.get("reward") or 0 for s in d["steps"][-1]]
        print("")
        print("=== %s   us $%.0f vs %s $%.0f"
              % (os.path.basename(path).split("-")[1], rewards[seat],
                 names[1 - seat], rewards[1 - seat]))
        show("ours", *profile_steps(d["steps"], seat))


def from_agent(agent, seed):
    """Run the local agent once and profile it the same way."""
    from kaggle_environments import make
    env = make("kaggriculture", configuration={"seed": seed}, debug=False)
    env.run([agent, "starter"])
    steps = [[{"observation": s[0]["observation"], "action": s[0].get("action")},
              {"observation": s[1].get("observation", {}),
               "action": s[1].get("action")}] for s in env.steps]
    print("")
    print("=== %s (local, seed %d)  bank $%.0f"
          % (agent, seed, env.steps[-1][0].reward or 0))
    show("ours", *profile_steps(steps, 0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replays", default=None)
    ap.add_argument("--agent", default=None)
    ap.add_argument("--seed", type=int, default=1000)
    args = ap.parse_args()
    if args.replays:
        from_replays(args.replays)
    if args.agent:
        from_agent(args.agent, args.seed)


if __name__ == "__main__":
    main()
