"""Search the whole allocation jointly, against the real simulator.

The complaint this answers: every acreage constant in `main.py` was fitted on
its own with the others held still, which is the wrong shape of answer when
the goods compete for the same tiles, the same crew and the same market.

The first two attempts at fixing that built a *surrogate* -- a model of the
season cheap enough to search exhaustively. Both failed (see `allocate.py` and
`season_model.py`): the steady-state one ranked known results backwards four
times in five, and the day-indexed one, though calibrated to within 9% of the
real mirror bank, still only reached 5/10 on retrodiction. It over-produces
melon by 48%, and melon is a race whose value is almost entirely in timing.

The conclusion is that no surrogate is needed. We already own an exact model
of the season -- the environment -- and a game costs about 35 seconds. What
was actually missing was a search that moves every knob *together*.

So this is coordinate descent over the full allocation vector, evaluated by
`eval.py` on paired seeds, cycling until no single move improves. It is slower
than a surrogate and it is trustworthy, which the surrogates were not.

    py -3.12 optimize.py --games 6 --rounds 2

Bank against `starter` is the search signal because it is cheap and dense;
it is a filter, not the objective. Whatever this returns must still be put
through `h2h.py` before it is believed -- five candidates on 20 August banked
better and lost the mirror.
"""
import argparse
import itertools
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

# The allocation vector. Values to try for each, around the incumbent.
AXES = {
    "N_COWS": [4, 6, 8, 10, 12],
    "N_SHEEP": [0, 2, 4, 6, 8],
    "MELON_TILES": [16, 20, 24, 28, 32],
    "STRAWBERRY_TILES": [22, 28, 34, 40],
}
START = {"N_COWS": 8, "N_SHEEP": 4, "MELON_TILES": 24, "STRAWBERRY_TILES": 34}


def evaluate(combo, games, seed, workers_env=None):
    env = dict(os.environ)
    env.update({"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"})
    for k, v in combo.items():
        env["KAG_" + k] = str(v)
    out = subprocess.run(
        [sys.executable, "eval.py", "--json", "--games", str(games),
         "--seed", str(seed)],
        capture_output=True, text=True, env=env, timeout=3600).stdout
    for line in reversed(out.strip().splitlines()):
        if line.startswith("{"):
            got = json.loads(line)
            if got.get("crashed"):
                return None
            return got["median"]
    return None


def key(combo):
    return tuple(sorted(combo.items()))


CACHE = "optimize_cache.json"


def load_cache():
    """Scores already paid for. A run costs minutes; losing them to a crash
    once was enough."""
    try:
        with open(CACHE) as f:
            return {tuple(tuple(x) for x in k): v
                    for k, v in (json.loads(line) for line in f if line.strip())}
    except IOError:
        return {}


def save_score(k, value):
    with open(CACHE, "a") as f:
        json.dump([[list(p) for p in k], value], f)
        f.write(os.linesep)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=6)
    ap.add_argument("--seed", type=int, default=1000)
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--random", type=int, default=0,
                    help="also sample N allocations that move every axis at "
                         "once; coordinate descent alone cannot see those")
    args = ap.parse_args()

    seen = load_cache()
    if seen:
        print("reusing %d cached evaluations" % len(seen))
    current = dict(START)

    def score(combo):
        k = key(combo)
        if k not in seen:
            seen[k] = evaluate(combo, args.games, args.seed)
            save_score(k, seen[k])
        return seen[k]

    base = score(current)
    print("start %s -> $%s" % (current, format(base or 0, ",")))

    for rnd in range(args.rounds):
        improved = False
        for axis, values in AXES.items():
            cands = []
            for v in values:
                if v == current[axis]:
                    continue
                trial = dict(current)
                trial[axis] = v
                if key(trial) not in seen:
                    cands.append(trial)
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                for trial, fut in [(c, pool.submit(score, c)) for c in cands]:
                    fut.result()

            best, best_score = current, base
            for v in values:
                trial = dict(current)
                trial[axis] = v
                got = seen.get(key(trial))
                if got is not None and got > (best_score or 0):
                    best, best_score = trial, got
            if best_score and best_score > (base or 0):
                print("  round %d  %-18s %s -> %s   $%s"
                      % (rnd + 1, axis, current[axis], best[axis],
                         format(best_score, ",")))
                current, base, improved = best, best_score, True
            else:
                print("  round %d  %-18s no move (best stays %s)"
                      % (rnd + 1, axis, current[axis]))
        if not improved:
            print("  round %d: no axis improved, converged" % (rnd + 1))
            break

    if args.random:
        import random
        rng = random.Random(7)
        trials = []
        while len(trials) < args.random:
            t = {a: rng.choice(v) for a, v in AXES.items()}
            if key(t) not in seen and t not in trials:
                trials.append(t)
        print("")
        print("sampling %d simultaneous multi-axis moves" % len(trials))
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for fut in [pool.submit(score, t) for t in trials]:
                fut.result()
        ranked = sorted(((seen[key(t)] or 0, t) for t in trials),
                        key=lambda kv: kv[0], reverse=True)
        for sc, t in ranked[:6]:
            flag = "  <-- BEATS INCUMBENT" if sc > (base or 0) else ""
            print("  $%-12s %s%s" % (format(sc, ","), t, flag))
        if ranked and ranked[0][0] > (base or 0):
            base, current = ranked[0]
            print("  a diagonal move wins; goods do interact")
        else:
            print("  none beat the coordinate-descent optimum")

    print("")
    print("best allocation found: %s" % current)
    print("bank vs starter: $%s  (incumbent $%s)"
          % (format(base or 0, ","), format(seen.get(key(START)) or 0, ",")))
    print("")
    print("NOT a result yet. Confirm with:")
    print("  py -3.12 h2h.py <variant> --base main.py --games 12")


if __name__ == "__main__":
    main()
