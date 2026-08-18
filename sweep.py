"""
Parameter sweep over the agent's policy constants.

    py -3.12 sweep.py TILES_PER_UNIT=6,8,10,12
    py -3.12 sweep.py MAX_LAND=0,1,2,3 MAX_HANDS=4,8,12 --games 8
    py -3.12 sweep.py --games 12 --workers 6 TILES_PER_UNIT=8,10

Each argument of the form `NAME=v1,v2,...` names a knob that `main.py` reads
through `_P()` (as `KAG_NAME`) and the values to try. The cross product is run,
every configuration against the same seeds, and the results are printed sorted
by median final balance.

Two things make this trustworthy enough to act on:

- **Paired seeds.** Every configuration plays the identical set of games, so
  differences are not weed spawns and shop draws. Without this, a batch of ten
  is far too noisy to separate configurations a few hundred dollars apart.
- **Crashes are never scored.** A configuration whose agent fails to finish is
  reported as CRASH, not as a bad policy.

Configurations run in parallel as subprocesses, since a single game is about
five seconds and a grid is otherwise unusable.
"""
import argparse
import itertools
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor


def run_config(combo, games, seed, opponent, agent):
    env = dict(os.environ)
    # kaggle_environments drags in numpy/OpenBLAS, which spins up a thread pool
    # per process and exhausts memory once several games run side by side.
    env.update({"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"})
    for name, value in combo.items():
        env["KAG_" + name] = str(value)
    cmd = [sys.executable, "eval.py", "--json",
           "--games", str(games), "--seed", str(seed),
           "--opponent", opponent, "--agent", agent]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    line = ""
    for candidate in reversed(proc.stdout.strip().splitlines()):
        if candidate.startswith("{"):
            line = candidate
            break
    if not line:
        return combo, {"error": (proc.stderr or proc.stdout).strip()[-300:]}
    return combo, json.loads(line)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("knobs", nargs="*", help="NAME=v1,v2,...")
    ap.add_argument("--games", type=int, default=8)
    ap.add_argument("--seed", type=int, default=1000,
                    help="base seed; every configuration plays the same games")
    ap.add_argument("--opponent", default="starter")
    ap.add_argument("--agent", default="main.py")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    if not args.knobs:
        sys.exit("nothing to sweep. e.g. py -3.12 sweep.py TILES_PER_UNIT=6,8,10")

    names, value_lists = [], []
    for knob in args.knobs:
        name, _, values = knob.partition("=")
        if not values:
            sys.exit(f"expected NAME=v1,v2,... but got {knob!r}")
        names.append(name)
        value_lists.append(values.split(","))

    combos = [dict(zip(names, values)) for values in itertools.product(*value_lists)]
    print(f"{len(combos)} configurations x {args.games} games "
          f"(seeds {args.seed}..{args.seed + args.games - 1}) "
          f"vs {args.opponent}, {args.workers} workers\n")

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_config, c, args.games, args.seed,
                               args.opponent, args.agent) for c in combos]
        for future in futures:
            combo, result = future.result()
            results.append((combo, result))
            label = " ".join(f"{k}={v}" for k, v in combo.items())
            if "error" in result:
                print(f"  {label:<40} ERROR {result['error']}")
            elif result["crashed"]:
                print(f"  {label:<40} CRASH ({result['crashed']} of {result['games']})")
            else:
                print(f"  {label:<40} median ${result['median']:>8,.0f}  "
                      f"[{result['min']:>7,.0f}..{result['max']:>7,.0f}]  "
                      f"{result['wins']}W{result['draws']}D{result['losses']}L  "
                      f"{result['elapsed']}s")

    ok = [(c, r) for c, r in results if "error" not in r and not r["crashed"]]
    ok.sort(key=lambda cr: cr[1]["median"], reverse=True)
    print("\nranked by median:")
    for combo, result in ok:
        label = " ".join(f"{k}={v}" for k, v in combo.items())
        print(f"  ${result['median']:>9,.0f}  {label}")

    if len(results) != len(ok):
        sys.exit(1)


if __name__ == "__main__":
    main()
