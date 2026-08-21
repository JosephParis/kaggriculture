"""Score one knob-set against the ghosts of our own submitted builds.

The rival ghosts in `opponents/` do not survive being replayed on a board they
never saw -- `ghost_rival_top` banks $311 against the $119,914 it originally
scored, and `opp_floth` banks $0 -- so they win nothing and tell us nothing.
The ghosts of *our own* submissions do transfer (within 9-35% of their
original banks), and they are the builds we actually have to beat.

    py -3.12 score_ghosts.py                       # incumbent
    py -3.12 score_ghosts.py --knobs N_COWS=4,N_SHEEP=2 --games 6

Reports wins per ghost and the total, which is the objective.
"""
import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

GHOSTS = ["ghost_792", "ghost_804", "ghost_804b"]


def run(opponent, games, seed, knobs):
    env = dict(os.environ)
    env.update({"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"})
    for pair in (knobs or "").split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            env["KAG_" + k.strip()] = v.strip()
    out = subprocess.run(
        [sys.executable, "eval.py", "--json", "--games", str(games),
         "--seed", str(seed), "--opponent",
         os.path.join("opponents", opponent + ".py")],
        capture_output=True, text=True, env=env, timeout=3600).stdout
    for line in reversed(out.strip().splitlines()):
        if line.startswith("{"):
            return json.loads(line)
    return None


def score(knobs, games=6, seed=3000, workers=3, quiet=False):
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [(g, pool.submit(run, g, games, seed, knobs)) for g in GHOSTS]
        rows = [(g, f.result()) for g, f in futs]
    wins = total = 0
    banks = []
    for g, got in rows:
        if not got:
            continue
        wins += got["wins"]
        total += got["wins"] + got["losses"] + got["draws"]
        banks.append(got["median"])
        if not quiet:
            print("  %-12s %dW%dL   bank $%s"
                  % (g, got["wins"], got["losses"], format(got["median"], ",")))
    if not quiet:
        print("  %-12s %d/%d   median bank $%s"
              % ("TOTAL", wins, total,
                 format(sorted(banks)[len(banks) // 2] if banks else 0, ",")))
    return wins, total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--knobs", default="")
    ap.add_argument("--games", type=int, default=6)
    ap.add_argument("--seed", type=int, default=3000)
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    print("[%s]" % (args.knobs or "defaults"))
    score(args.knobs, args.games, args.seed, args.workers)


if __name__ == "__main__":
    main()
