"""Score every DAgger checkpoint against the heuristic it was cloned from.

Three things are checked for each set of weights, and the first is not
optional: **that the policy is actually driving**. A checkpoint whose encoder
no longer matches the feature builder loads, throws, gets swallowed, and the
agent runs pure heuristic -- which reads as a flawless clone. That happened
here once already, so every row reports how many times the learned scorer was
consulted, and a row with zero is a fallback, not a result.

    py -3.12 eval_checkpoints.py [--games 6] [--seeds 3000,5000]

Bank against `starter` is the cheap signal; the ghost panel is the one that
tracks the ladder, such as it does.
"""
import argparse
import glob
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

PROBE = r'''
import os, main
from kaggle_environments import make
orig = main._best_task_at
used = [0]
def spy(b, c, p, scorer=None):
    if scorer is not None:
        used[0] += 1
    return orig(b, c, p, scorer)
main._best_task_at = spy
env = make("kaggriculture", configuration={"seed": int(os.environ["PSEED"])},
           debug=False)
env.run([main.agent, os.environ["POPP"]])
import json
print(json.dumps({"bank": float(env.steps[-1][0].reward or 0),
                  "used": used[0],
                  "them": float(env.steps[-1][1].reward or 0)}))
'''


def one(weights, seed, opponent):
    env = dict(os.environ)
    env.update({"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
                "PYTHONPATH": ".", "PSEED": str(seed), "POPP": opponent})
    if weights:
        env["KAG_LEARNED_UNITS"] = "2"
        env["KAG_WEIGHTS"] = weights
    else:
        env["KAG_LEARNED_UNITS"] = "0"
    out = subprocess.run([sys.executable, "-c", PROBE], env=env,
                         capture_output=True, text=True, timeout=3600).stdout
    for line in reversed(out.strip().splitlines()):
        if line.startswith("{"):
            return json.loads(line)
    return None


def score(weights, seeds, games, opponent, workers):
    jobs = [(s + g) for s in seeds for g in range(games)]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        res = [f.result() for f in
               [pool.submit(one, weights, s, opponent) for s in jobs]]
    res = [r for r in res if r]
    if not res:
        return None
    banks = sorted(r["bank"] for r in res)
    wins = sum(1 for r in res if r["bank"] > r["them"])
    return {"median": banks[len(banks) // 2],
            "wins": wins, "n": len(res),
            "used": sum(r["used"] for r in res)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=4)
    ap.add_argument("--seeds", default="3000,5000")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--ghost", default="opponents/ghost_804.py")
    args = ap.parse_args()
    seeds = [int(x) for x in args.seeds.split(",")]

    ckpts = [None] + sorted(glob.glob(os.path.join("weights", "dagger*.npz")))
    print("%d games a seed over seeds %s" % (args.games, seeds))
    print("")
    print("  %-16s %14s %10s %14s %10s" %
          ("checkpoint", "vs starter", "scorer", "vs ghost_804", "wins"))
    for c in ckpts:
        name = "heuristic" if c is None else os.path.basename(c)[:-4]
        st = score(c, seeds, args.games, "starter", args.workers)
        gh = score(c, seeds, args.games, args.ghost, args.workers)
        if not st or not gh:
            print("  %-16s ERROR" % name)
            continue
        flag = ""
        if c is not None and st["used"] == 0:
            flag = "  <- NOT DRIVING (fallback)"
        print("  %-16s %14s %10d %14s %6d/%-3d%s"
              % (name, "$" + format(int(st["median"]), ","), st["used"],
                 "$" + format(int(gh["median"]), ","), gh["wins"], gh["n"],
                 flag))


if __name__ == "__main__":
    main()
