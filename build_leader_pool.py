"""Reduce leader replays to the target-cell pool `train_target.py` reads.

Same labelling as the DAgger pool -- board planes per turn, plus the cell each
unit was sent to -- built from replays instead of expert rollouts. Two things
differ from the version in `kaggle_train_notebook.py`:

  * **Per-seat observations.** `nn_features.encode` reads `obs["private"]` for
    the seed and shed channels, and `private` is per-player. Reading
    `steps[i][0]["observation"]` for both seats puts player 0's seeds and shed
    on every seat-1 board -- five of forty-six channels wrong on half the
    data, and silent.
  * **The boards are stored once.** Writing `Btr=B, Bte=B` puts the whole
    board array in the file twice, which at this size is gigabytes of file and
    of load-time memory for nothing. The split is materialised instead, with
    the test gather indices rebased.

    py -3.12 build_leader_pool.py --replays data/leader_replays --out pool.npz
    py -3.12 build_leader_pool.py --shards data/shards --out pool.npz

`--shards` merges the per-episode `.npz` files written by a streaming pull,
for when the raw replays are too big to keep (~30 MB each).
"""
import argparse
import glob
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

STRIDE = 2


def extract(path):
    """Board planes and per-unit target cells for the winning seat(s)."""
    import nn_features as F

    boards, gather, targets = [], [], []
    try:
        with open(path) as fh:
            d = json.load(fh)
    except Exception:                                  # noqa: BLE001
        return None
    steps = d.get("steps") or []
    if not steps:
        return None
    rew = [s.get("reward") or 0 for s in steps[-1]]
    for seat in (0, 1):
        if rew[seat] < rew[1 - seat]:
            continue                  # imitate the winner of each game only
        for i in range(0, len(steps) - 1, STRIDE):
            if seat >= len(steps[i]) or seat >= len(steps[i + 1]):
                break
            obs = steps[i][seat]["observation"]
            nxt = steps[i + 1][seat]["observation"]
            if "farms" not in obs or "farms" not in nxt:
                break
            farm = obs["farms"][seat]
            units = [farm.get("farmer")] + list(farm.get("hands") or [])
            nfarm = nxt["farms"][seat]
            nunits = [nfarm.get("farmer")] + list(nfarm.get("hands") or [])
            planes = F.encode(obs, seat)
            bi = len(boards)
            added = False
            for u, pos in enumerate(units):
                if not pos or u >= len(nunits) or not nunits[u]:
                    continue
                # A unit that moved reveals its heading; one that acted in
                # place is labelled with its own cell.
                nx, ny = nunits[u]
                x, y = pos
                tx, ty = (nx, ny) if (nx, ny) != (x, y) else (x, y)
                gather.append((bi, int(y), int(x)))
                targets.append(int(ty) * 10 + int(tx))
                added = True
            if added:
                boards.append(planes.astype(np.float16))
    if not boards:
        return None
    return (np.asarray(boards, dtype=np.float16),
            np.asarray(gather, dtype=np.int32),
            np.asarray(targets, dtype=np.int16))


def from_shard(path):
    z = np.load(path)
    return z["b"], z["g"], z["t"]


def collect(items, fn, workers):
    """Concatenate per-episode arrays, rebasing each one's board indices."""
    B, G, T, off = [], [], [], 0
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for n, got in enumerate(pool.map(fn, items)):
            if got is None:
                continue
            b, g, t = got
            g = g.copy()
            g[:, 0] += off
            off += len(b)
            B.append(b)
            G.append(g)
            T.append(t)
            if n % 25 == 0:
                print("  %d/%d  %d boards  (%.0fs)"
                      % (n, len(items), off, time.time() - t0), flush=True)
    if not B:
        raise SystemExit("nothing extracted")
    return np.concatenate(B), np.concatenate(G), np.concatenate(T)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replays", default=None)
    ap.add_argument("--shards", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    if bool(args.replays) == bool(args.shards):
        raise SystemExit("give exactly one of --replays or --shards")

    if args.replays:
        items = sorted(glob.glob(os.path.join(args.replays,
                                              "episode-*.json")))
        fn = extract
    else:
        items = sorted(glob.glob(os.path.join(args.shards, "ep-*.npz")))
        fn = from_shard
    print("inputs: %d" % len(items), flush=True)

    B, G, T = collect(items, fn, args.workers)
    print("dataset: %d boards, %d labelled unit-targets" % (len(B), len(T)))
    print("target spread: %d distinct cells, most common %d%% of labels"
          % (len(np.unique(T)), round(100 * np.bincount(T).max() / len(T))))
    print("stayed put: %d%%"
          % round(100 * np.mean(T == (G[:, 1] * 10 + G[:, 2]))))

    # Hold out the last tenth of *boards*, so the split falls between games
    # rather than between turns of one game.
    cut = int(len(B) * 0.9)
    mtr, mte = G[:, 0] < cut, G[:, 0] >= cut
    Gte = G[mte].copy()
    Gte[:, 0] -= cut                       # rebase onto the test board slice
    np.savez_compressed(args.out,
                        Btr=B[:cut], Gtr=G[mtr], Ttr=T[mtr],
                        Bte=B[cut:], Gte=Gte, Tte=T[mte])
    print("wrote %s  (%d train / %d test samples, %.2f GB of boards)"
          % (args.out, int(mtr.sum()), int(mte.sum()), B.nbytes / 1e9))


if __name__ == "__main__":
    main()
