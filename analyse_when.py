"""In a loss, *when* does the game get away from us?

Earlier replay work compared season totals -- what each farm sold by the end.
That says what the winner had more of; it does not say when the gap opened,
and the two want different fixes. A gap that appears on day 5 is an opening
problem, one that appears on day 22 is an endgame problem, and a farm that
leads until day 25 and loses is a different failure again.

This walks each loss day by day and reports the bank on both sides, the lead,
and the day the lead was last ours.

    py -3.12 analyse_when.py [--dir replays]
"""
import argparse
import collections
import glob
import json
import os

ME = "Joseph Paris"


def ascii_name(n):
    """Opponent names carry accents and the Windows console is cp1252."""
    return (n or "?").encode("ascii", "replace").decode("ascii")


def bank_series(steps, seat, days=30):
    """Bank at the end of each day."""
    out = {}
    for step in steps:
        obs = step[0]["observation"]
        farm = obs["farms"][seat]
        out[obs["day"]] = farm["money"]
    return [out.get(d, 0) for d in range(days)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="replays")
    ap.add_argument("--days", type=int, default=30)
    args = ap.parse_args()

    paths = sorted(glob.glob(os.path.join(args.dir, "*-replay.json")))
    swings = collections.Counter()
    losses = 0
    lead_lost_on = []

    for path in paths:
        with open(path) as f:
            d = json.load(f)
        names = [a.get("Name") for a in d.get("info", {}).get("Agents", [])]
        mine = 0 if names and names[0] == ME else 1
        them = 1 - mine
        rewards = [s.get("reward") or 0 for s in d["steps"][-1]]
        if rewards[mine] >= rewards[them]:
            continue
        losses += 1
        a = bank_series(d["steps"], mine, args.days)
        b = bank_series(d["steps"], them, args.days)

        last_ahead = None
        for day in range(args.days):
            if a[day] > b[day]:
                last_ahead = day
        lead_lost_on.append(last_ahead)

        print("")
        print("=== %s   final $%s vs %s $%s   (lead last held: %s)"
              % (os.path.basename(path).split("-")[1],
                 format(int(rewards[mine]), ","), ascii_name(names[them]),
                 format(int(rewards[them]), ","),
                 "day %d" % last_ahead if last_ahead is not None else "never"))
        print("  %5s %10s %10s %10s" % ("day", "ours", "theirs", "lead"))
        for day in range(0, args.days, 3):
            lead = a[day] - b[day]
            print("  %5d %10s %10s %+10s"
                  % (day, format(int(a[day]), ","), format(int(b[day]), ","),
                     format(int(lead), ",")))
        # where the gap widened most
        worst_day, worst = None, 0
        for day in range(1, args.days):
            delta = (a[day] - b[day]) - (a[day - 1] - b[day - 1])
            if delta < worst:
                worst, worst_day = delta, day
        if worst_day is not None:
            swings[worst_day] += 1
            print("  worst single day: day %d, lead moved %s"
                  % (worst_day, format(int(worst), ",")))

    if not losses:
        print("no losses in %s" % args.dir)
        return
    print("")
    print("across %d losses" % losses)
    never = sum(1 for x in lead_lost_on if x is None)
    print("  never led at all            : %d" % never)
    held = [x for x in lead_lost_on if x is not None]
    if held:
        held.sort()
        print("  of those that led, lost it  : median day %d (range %d-%d)"
              % (held[len(held) // 2], held[0], held[-1]))
    print("  worst-swing day, most common: %s"
          % ", ".join("day %d x%d" % (d, n) for d, n in swings.most_common(5)))


if __name__ == "__main__":
    main()
