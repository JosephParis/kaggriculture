"""
Score candidates against a panel of opponents, not just a mirror of ourselves.

    py -3.12 panel.py cand_*.py --panel starter spar_cow.py spar_melon.py

Mirror-only testing has a systematic bias: when both sides run the same build
they dump the same premium goods on the same turn and crash each other, which
punishes melon-heavy strategies far harder than the real ladder does. The
public notebooks describe the field as a handful of distinct clusters -- cow
ranch, melon IPO, staged herd -- so a candidate is judged here on aggregate
win rate across several of them, from both seats.
"""
import argparse, json, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

def run(agent, opponent, games, seed):
    env = dict(os.environ)
    env.update({"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"})
    out = subprocess.run([sys.executable, "eval.py", "--json", "--agent", agent,
                          "--opponent", opponent, "--games", str(games),
                          "--seed", str(seed)],
                         capture_output=True, text=True, env=env)
    for line in reversed(out.stdout.strip().splitlines()):
        if line.startswith("{"):
            return json.loads(line)
    return {"error": (out.stderr or out.stdout)[-200:]}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidates", nargs="+")
    ap.add_argument("--panel", nargs="+", required=True)
    ap.add_argument("--games", type=int, default=6)
    ap.add_argument("--seed", type=int, default=7000)
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs = {}
        for c in args.candidates:
            for p in args.panel:
                if os.path.basename(p) == os.path.basename(c):
                    continue
                jobs[(c, p, 0)] = pool.submit(run, c, p, args.games, args.seed)
                jobs[(c, p, 1)] = pool.submit(run, p, c, args.games, args.seed)

        table = {}
        for (c, p, seat), fut in jobs.items():
            r = fut.result()
            if "error" in r:
                print(f"  ERROR {c} vs {p}: {r['error']}")
                continue
            w, l = (r["wins"], r["losses"]) if seat == 0 else (r["losses"], r["wins"])
            cw, cl, cd = table.get((c, p), (0, 0, 0))
            table[(c, p)] = (cw + w, cl + l, cd + r["draws"])

    print(f"\n{'candidate':<18}" + "".join(f"{os.path.basename(p)[:13]:>15}" for p in args.panel)
          + f"{'TOTAL':>12}")
    rows = []
    for c in args.candidates:
        cells, tw, tl = "", 0, 0
        for p in args.panel:
            if (c, p) not in table:
                cells += f"{'--':>15}"
                continue
            w, l, d = table[(c, p)]
            tw += w; tl += l
            cells += f"{f'{w}-{l}':>15}"
        pct = tw / (tw + tl) * 100 if tw + tl else 0
        rows.append((pct, c, tw, tl))
        print(f"{os.path.basename(c):<18}{cells}{f'{tw}-{tl} ({pct:.0f}%)':>12}")
    print("\nranked by aggregate win rate:")
    for pct, c, tw, tl in sorted(rows, reverse=True):
        print(f"  {pct:5.1f}%  {os.path.basename(c):<18} {tw}-{tl}")

if __name__ == "__main__":
    main()
