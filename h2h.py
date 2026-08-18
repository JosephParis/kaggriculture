"""
Head-to-head comparison, both seats, paired seeds.

    py -3.12 h2h.py var_d.py var_e.py --base var_a.py --games 8

The ladder rates on win/loss/tie only -- coin margin buys no rating -- so a
candidate has to be judged by whether it *beats* the incumbent, not by what it
banks against `starter`. This matters: two configurations that were within
$600 of each other on bank vs `starter` went 11-5 head to head.

Each candidate plays the base from both seats, because seat matters: market
orders and hiring resolve in player order.
"""
import argparse, json, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

def run(agent, opponent, games, seed):
    env = dict(os.environ)
    env.update({"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"})
    out = subprocess.run(
        [sys.executable, "eval.py", "--json", "--agent", agent,
         "--opponent", opponent, "--games", str(games), "--seed", str(seed)],
        capture_output=True, text=True, env=env)
    for line in reversed(out.stdout.strip().splitlines()):
        if line.startswith("{"):
            return json.loads(line)
    return {"error": (out.stderr or out.stdout)[-200:]}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidates", nargs="+")
    ap.add_argument("--base", default="var_a.py")
    ap.add_argument("--games", type=int, default=8)
    ap.add_argument("--seed", type=int, default=4000)
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()

    jobs = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for c in args.candidates:
            jobs.append((c, pool.submit(run, c, args.base, args.games, args.seed),
                            pool.submit(run, args.base, c, args.games, args.seed)))
        rows = []
        for c, f_seat0, f_seat1 in jobs:
            a, b = f_seat0.result(), f_seat1.result()
            if "error" in a or "error" in b:
                print(f"  {c:<16} ERROR {a.get('error') or b.get('error')}")
                continue
            # Candidate wins: its own wins in seat 0, plus base's losses in seat 1.
            w = a["wins"] + b["losses"]
            l = a["losses"] + b["wins"]
            d = a["draws"] + b["draws"]
            rows.append((w - l, c, w, l, d))
            print(f"  {c:<16} {w:>2}W {l:>2}L {d}D vs {args.base}   "
                  f"(seat0 {a['wins']}-{a['losses']}, seat1 {b['losses']}-{b['wins']})")
    print(f"\nranked by margin over {args.base}:")
    for margin, c, w, l, d in sorted(rows, reverse=True):
        verdict = "BETTER" if margin > 0 else ("worse" if margin < 0 else "tied")
        print(f"  {margin:+3d}  {c:<16} {w}-{l}-{d}  {verdict}")

if __name__ == "__main__":
    main()
