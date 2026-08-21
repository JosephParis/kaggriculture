"""Size the prize in per-unit tour planning, before anyone builds one.

Issue 03 asks for the tour to be sized before it is built. Movement is 42.8%
of unit-actions, but that is not the prize: some of that walking is
unavoidable, and some of what a tour would save would be handed straight back
as idle, because 23.8% of actions are already `PASS`.

The method holds the workload fixed. For each unit on each day we record the
tiles it actually acted on, in order, and the movement it actually spent. Then
we ask what that *same* day's work would have cost with perfect routing: the
shortest path from where the unit started, through every tile it stopped at.

    actual movement - optimal path = what a tour could have saved

This is deliberately an over-estimate of the achievable saving, on three
counts, so what it produces is a ceiling and not a forecast:

  - It reorders the day with hindsight. A real tour is planned in the morning
    and the work appears during the day -- a plant ripens, an animal gets
    hungry -- so it cannot know the stop list in advance.
  - It ignores time windows. A tile watered in the morning and harvested in
    the afternoon is two stops here, and the optimiser is free to put them
    next to each other even though growth happens in between.
  - It assumes a saved step becomes productive work. It very often cannot:
    a unit that finishes early just idles, which is why the report splits
    savings by whether the unit had idle time that day.

Runs against `starter`, which is the cheap opponent; the mirror would move the
workload but not the geometry.

    py -3.12 tour_ceiling.py [--games 3] [--seed 1000]
"""
import argparse
import collections
import itertools

import main

MOVES = {"NORTH", "SOUTH", "EAST", "WEST"}


def _dist(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _path_len(order, start):
    total = 0
    pos = start
    for p in order:
        total += _dist(pos, p)
        pos = p
    return total


def _optimal_path(stops, start):
    """Shortest open path from `start` visiting every stop.

    Exact for short days by brute force; nearest-neighbour plus 2-opt beyond
    that. The approximation can only return a path at least as long as the
    true optimum, so it understates the saving -- which keeps this a ceiling
    on the prize rather than an inflated one.
    """
    if not stops:
        return 0
    if len(stops) <= 7:
        return min(_path_len(p, start) for p in itertools.permutations(stops))

    remaining = list(stops)
    order, pos = [], start
    while remaining:
        nxt = min(remaining, key=lambda p: _dist(pos, p))
        remaining.remove(nxt)
        order.append(nxt)
        pos = nxt

    best = _path_len(order, start)
    improved = True
    while improved:
        improved = False
        for i in range(len(order) - 1):
            for j in range(i + 2, len(order) + 1):
                cand = order[:i] + order[i:j][::-1] + order[j:]
                got = _path_len(cand, start)
                if got < best - 1e-9:
                    order, best, improved = cand, got, True
    return best


def main_cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=3)
    ap.add_argument("--opponent", default="starter")
    ap.add_argument("--seed", type=int, default=1000)
    args = ap.parse_args()

    from kaggle_environments import make

    # (game, day, unit) -> {"start", "stops", "move", "idle", "work"}
    days = {}
    tally = collections.Counter()
    game = [0]

    def traced(obs):
        me = obs["farms"][obs["player"]]
        positions = [tuple(me["farmer"])] + [tuple(h) for h in me["hands"]]
        out = main.agent(obs)
        ops = [out["farmer"]] + list(out["hands"])
        for i, op in enumerate(ops):
            if i >= len(positions):
                break
            tally[op[0]] += 1
            rec = days.setdefault((game[0], obs["day"], i),
                                  {"start": positions[i], "stops": [],
                                   "move": 0, "idle": 0, "work": 0})
            if op[0] in MOVES:
                rec["move"] += 1
            elif op[0] == "PASS":
                rec["idle"] += 1
            else:
                rec["work"] += 1
                # Consecutive actions on one tile are a single stop: the unit
                # is already standing there and walks nowhere between them.
                if not rec["stops"] or rec["stops"][-1] != positions[i]:
                    rec["stops"].append(positions[i])
        return out

    banks = []
    for g in range(args.games):
        game[0] = g
        env = make("kaggriculture", configuration={"seed": args.seed + g},
                   debug=False)
        env.run([traced, args.opponent])
        final = env.steps[-1]
        banks.append(final[0].reward if final[0].reward is not None else 0)

    actual = optimal = 0
    save_busy = save_idle = 0
    busy_days = idle_days = 0
    for rec in days.values():
        if not rec["stops"]:
            continue
        opt = _optimal_path(rec["stops"], rec["start"])
        actual += rec["move"]
        optimal += opt
        saved = max(0, rec["move"] - opt)
        if rec["idle"] > 0:
            save_idle += saved
            idle_days += 1
        else:
            save_busy += saved
            busy_days += 1

    total = sum(tally.values())
    games = float(args.games)
    moving = sum(v for k, v in tally.items() if k in MOVES)
    work = total - moving - tally.get("PASS", 0)
    per_work = (sum(banks) / float(len(banks))) / (work / games) if work else 0

    print(f"{args.games} game(s) vs {args.opponent}, seeds "
          f"{args.seed}..{args.seed + args.games - 1}")
    print(f"unit-actions {total}  movement {moving} "
          f"({100.0 * moving / total:.1f}%)  "
          f"productive {work} ({100.0 * work / total:.1f}%)")
    print(f"median bank ~${sum(banks) / len(banks):,.0f}, "
          f"so one productive action is worth about ${per_work:,.0f}\n")

    print(f"  movement actually spent      {actual / games:8.0f} /game")
    print(f"  perfect-routing lower bound  {optimal / games:8.0f} /game")
    print(f"  ceiling on what a tour saves {(actual - optimal) / games:8.0f} "
          f"/game  ({100.0 * (actual - optimal) / actual:.1f}% of movement)\n")

    print("  ...but a saved step only pays if the unit had no spare time:")
    print(f"    on unit-days with idle time  {save_idle / games:8.0f} /game "
          f"({idle_days} unit-days)  <- worth ~$0")
    print(f"    on unit-days with none       {save_busy / games:8.0f} /game "
          f"({busy_days} unit-days)  <- the real prize")
    print(f"\n  spendable ceiling: {save_busy / games:.0f} actions/game "
          f"~= ${save_busy / games * per_work:,.0f}/game at "
          f"${per_work:,.0f}/action")
    print("  (an over-estimate on every count -- see the module docstring)")


if __name__ == "__main__":
    main_cli()
