"""Build a training set from episode replays.

Each replay carries both players' observations and actions, so one episode is
about 13,800 labelled unit-actions. The board is encoded **once per turn per
seat** and every unit on it gathers from that shared encoding -- encoding
per-unit would multiply the storage by eleven for the same information.

Samples are labelled with the seat's final bank, so training can weight or
filter by how well that farm actually did. The winning side of a game we lost
is a demonstration from an agent better than ours, which is the whole reason
this data is worth having.

    py -3.12 nn_dataset.py --out data/bc.npz [--winners-only] [--stride 2]
"""
import argparse
import glob
import json
import os

import numpy as np

import nn_features as F

ME = "Joseph Paris"


def carry_of(obs, unit_ix):
    inv = (obs.get("private") or {}).get("inventories") or []
    if unit_ix < len(inv):
        return float(sum((inv[unit_ix] or {}).values()))
    return 0.0


def build(paths, stride, winners_only, max_boards=None):
    boards, gather, labels, carry, meta = [], [], [], [], []
    for path in paths:
        try:
            with open(path) as fh:
                d = json.load(fh)
        except Exception:
            continue
        names = [a.get("Name") for a in d.get("info", {}).get("Agents", [])]
        steps = d["steps"]
        rewards = [s.get("reward") or 0 for s in steps[-1]]
        seats = [0, 1]
        if winners_only:
            seats = [0 if rewards[0] > rewards[1] else 1]

        for t in range(0, len(steps), stride):
            step = steps[t]
            for seat in seats:
                obs = step[seat].get("observation")
                if not obs or "farms" not in obs:
                    obs = step[0].get("observation")
                act = step[seat].get("action")
                if not isinstance(act, dict) or not obs:
                    continue
                ops = [act.get("farmer")] + list(act.get("hands") or [])
                pos = F.unit_positions(obs, seat)
                pairs = [(i, p, o) for i, (p, o) in enumerate(zip(pos, ops))
                         if p and o and o[0] in F.OP_IX]
                if not pairs:
                    continue
                bi = len(boards)
                boards.append(F.encode(obs, seat).astype(np.float16))
                for i, p, o in pairs:
                    gather.append((bi, int(p[1]), int(p[0])))
                    labels.append(F.OP_IX[o[0]])
                    carry.append(carry_of(obs, i))
                meta.append((rewards[seat], rewards[1 - seat]))
            if max_boards and len(boards) >= max_boards:
                break
        print("  %-34s %6d boards %8d samples"
              % (os.path.basename(path)[:34], len(boards), len(labels)))
        if max_boards and len(boards) >= max_boards:
            break

    return (np.asarray(boards, dtype=np.float16),
            np.asarray(gather, dtype=np.int32),
            np.asarray(labels, dtype=np.int8),
            np.asarray(carry, dtype=np.float16),
            np.asarray(meta, dtype=np.float32))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="replays")
    ap.add_argument("--out", default="data/bc.npz")
    ap.add_argument("--stride", type=int, default=2,
                    help="take every Nth turn; consecutive turns are nearly "
                         "identical so this costs little and halves the size")
    ap.add_argument("--winners-only", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--holdout", type=int, default=4,
                    help="replays held out entirely, so evaluation never sees "
                         "a frame from a game it was trained on")
    args = ap.parse_args()

    paths = sorted(glob.glob(os.path.join(args.dir, "*-replay.json")))
    if args.limit:
        paths = paths[:args.limit]
    if len(paths) <= args.holdout:
        raise SystemExit("need more replays than the holdout")
    tr, te = paths[args.holdout:], paths[:args.holdout]
    print("%d replays: %d train, %d held out" % (len(paths), len(tr), len(te)))

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    print("train:")
    Btr, Gtr, Ytr, Ctr, Mtr = build(tr, args.stride, args.winners_only)
    print("holdout:")
    Bte, Gte, Yte, Cte, Mte = build(te, args.stride, args.winners_only)

    np.savez_compressed(args.out,
                        Btr=Btr, Gtr=Gtr, Ytr=Ytr, Ctr=Ctr, Mtr=Mtr,
                        Bte=Bte, Gte=Gte, Yte=Yte, Cte=Cte, Mte=Mte)
    mb = os.path.getsize(args.out) / 1e6
    print("")
    print("wrote %s  (%.0f MB)" % (args.out, mb))
    print("  train %d boards / %d samples" % (len(Btr), len(Ytr)))
    print("  test  %d boards / %d samples" % (len(Bte), len(Yte)))
    counts = np.bincount(Ytr.astype(int), minlength=F.N_OPS)
    top = np.argsort(-counts)[:6]
    print("  most common ops: %s"
          % ", ".join("%s %.0f%%" % (F.OPS[c], 100 * counts[c] / counts.sum())
                      for c in top))


if __name__ == "__main__":
    main()
