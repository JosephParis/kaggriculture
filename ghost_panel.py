"""Score a build against a panel of ghosts, not one tape.

`optimize.py --opponent ghost_804.py` found a configuration that goes from 0
wins to 4 against a single replayed tape. That is exactly the shape of result
that overfits: eight seeds against one opponent's fixed actions.

This runs a candidate against every ghost in `opponents/` and reports wins per
ghost plus the total, so a configuration has to beat several different real
farms -- our own submitted builds *and* the rivals that beat them -- rather
than one.

    py -3.12 ghost_panel.py main.py [--games 6] [--seed 3000]
    py -3.12 ghost_panel.py --knobs N_COWS=4,N_SHEEP=2 --games 6

Ghosts replay a fixed 720-turn tape and cannot react, so a win is a
counterfactual rather than a true head to head. They are still the only way to
play the 804-rated submission, which exists nowhere but the ladder.
"""
import argparse
import glob
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor


def run(agent, opponent, games, seed, knobs):
    env = dict(os.environ)
    env.update({"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"})
    for pair in (knobs or "").split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            env["KAG_" + k.strip()] = v.strip()
    out = subprocess.run(
        [sys.executable, "eval.py", "--json", "--agent", agent,
         "--opponent", opponent, "--games", str(games), "--seed", str(seed)],
        capture_output=True, text=True, env=env, timeout=3600).stdout
    for line in reversed(out.strip().splitlines()):
        if line.startswith("{"):
            return json.loads(line)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("agent", nargs="?", default="main.py")
    ap.add_argument("--games", type=int, default=6)
    ap.add_argument("--seed", type=int, default=3000)
    ap.add_argument("--knobs", default="")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    ghosts = sorted(glob.glob(os.path.join("opponents", "*.py")))
    if not ghosts:
        print("no ghosts in opponents/")
        return

    label = args.knobs or "defaults"
    print("%s  [%s]  %d games a ghost, seeds %d+"
          % (args.agent, label, args.games, args.seed))

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [(g, pool.submit(run, args.agent, g, args.games, args.seed,
                                args.knobs)) for g in ghosts]
        rows = [(g, f.result()) for g, f in futs]

    total_w = total_n = 0
    for g, got in rows:
        name = os.path.basename(g).replace(".py", "")
        if not got:
            print("  %-22s ERROR" % name)
            continue
        w, n = got["wins"], got["wins"] + got["losses"] + got["draws"]
        total_w += w
        total_n += n
        print("  %-22s %d/%d   bank $%s vs $%s"
              % (name, w, n, format(got["median"], ","),
                 format(got.get("their_median", 0), ",")))
    print("  %-22s %d/%d" % ("TOTAL", total_w, total_n))


if __name__ == "__main__":
    main()
