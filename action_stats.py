"""Tally what the crew actually spends its actions on.

Score never shows this. Every significant problem in this agent so far has been
invisible in the bank and obvious in an action tally: the farm dying by day 6,
five birds pegged at `max_held`, and 72% of all actions being movement. That
72% predates `URGENCY_W=0` (18 August), so it needs re-measuring before any
further routing work is justified.

    py -3.12 action_stats.py [--games 3] [--opponent starter]

Reports the share of unit-actions by operation, and movement as a share of the
whole, which is the number issue 03 is trying to move.
"""
import argparse
import collections

import main

MOVES = {"NORTH", "SOUTH", "EAST", "WEST"}


def main_cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=3)
    ap.add_argument("--opponent", default="starter")
    ap.add_argument("--seed", type=int, default=1000)
    args = ap.parse_args()

    from kaggle_environments import make

    tally = collections.Counter()

    def traced(obs):
        out = main.agent(obs)
        for op in [out["farmer"]] + list(out["hands"]):
            tally[op[0]] += 1
        return out

    for g in range(args.games):
        env = make("kaggriculture", configuration={"seed": args.seed + g}, debug=False)
        env.run([traced, args.opponent])

    total = sum(tally.values())
    moving = sum(v for k, v in tally.items() if k in MOVES)
    idle = tally.get("PASS", 0)
    print(f"unit-actions over {args.games} game(s): {total}\n")
    for op, n in tally.most_common():
        print(f"  {op:<20} {n:>7}  {100.0 * n / total:5.1f}%")
    print(f"\n  movement             {moving:>7}  {100.0 * moving / total:5.1f}%")
    print(f"  idle (PASS)          {idle:>7}  {100.0 * idle / total:5.1f}%")
    print(f"  productive           {total - moving - idle:>7}  "
          f"{100.0 * (total - moving - idle) / total:5.1f}%")


if __name__ == "__main__":
    main_cli()
