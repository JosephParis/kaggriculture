"""
Local evaluation harness.

    py -3.12 eval.py                     # 10 games vs the starter agent
    py -3.12 eval.py --games 30
    py -3.12 eval.py --opponent random
    py -3.12 eval.py --replay out.json   # dump one replay for inspection

A single game says almost nothing: the market, weed spawns and shop unlocks all
carry randomness, so two runs of the same agent differ. Report a win rate over
a batch and the spread of final balances, never one number.

Nothing here submits. Submissions are rate-limited and cannot be withdrawn, so
they stay a manual step.
"""
import argparse
import json
import statistics
import sys
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=10)
    ap.add_argument("--opponent", default="starter", help="starter | random | pass | a .py path")
    ap.add_argument("--agent", default="main.py")
    ap.add_argument("--replay", default=None, help="write one replay JSON here")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    try:
        from kaggle_environments import make
    except ImportError:
        sys.exit("kaggle-environments is not installed. py -3.12 -m pip install -U kaggle-environments")

    wins = draws = losses = 0
    mine, theirs, crashed = [], [], 0
    t0 = time.time()

    for g in range(args.games):
        config = {}
        if args.seed is not None:
            config["seed"] = args.seed + g
        env = make("kaggriculture", configuration=config, debug=False)
        env.run([args.agent, args.opponent])

        final = env.steps[-1]
        r0 = final[0].reward if final[0].reward is not None else 0
        r1 = final[1].reward if final[1].reward is not None else 0

        # A crashed agent shows as a non-DONE status, and its reward is not
        # comparable -- counting it as a loss would hide the bug.
        if final[0].status != "DONE":
            crashed += 1
            print(f"  game {g+1}: AGENT DID NOT FINISH ({final[0].status})")
            continue

        mine.append(r0)
        theirs.append(r1)
        if r0 > r1:
            wins += 1
        elif r0 == r1:
            draws += 1
        else:
            losses += 1

        print(f"  game {g+1}: {r0} vs {r1}  {'win' if r0 > r1 else 'draw' if r0 == r1 else 'loss'}")

        if args.replay and g == 0:
            with open(args.replay, "w") as f:
                json.dump(env.toJSON(), f)
            print(f"  replay written to {args.replay}")

    played = len(mine)
    print()
    print(f"opponent      : {args.opponent}")
    print(f"games         : {args.games} ({played} finished, {crashed} crashed)")
    if played:
        print(f"record        : {wins}W {draws}D {losses}L   win rate {wins / played:.0%}")
        print(f"my balance    : median {statistics.median(mine):.0f}  "
              f"min {min(mine):.0f}  max {max(mine):.0f}")
        print(f"their balance : median {statistics.median(theirs):.0f}")
    print(f"elapsed       : {time.time() - t0:.1f}s")

    if crashed:
        sys.exit(1)


if __name__ == "__main__":
    main()
