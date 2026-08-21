"""Feasibility probe for behavioural cloning: can a model predict expert moves?

Before proposing to learn a policy, check that the signal is there. Every
replay carries both players' actions, so each episode is ~13,800 labelled
(state, unit-action) pairs -- and the *winning* side of every episode we lost
is a demonstration from an agent better than ours.

This extracts cheap per-unit features and fits a plain multinomial logistic
regression in numpy. It is deliberately the weakest reasonable model: if a
linear model on hand features already predicts far above the majority-class
baseline, a small conv net will do much better, and cloning is worth building.
If it barely beats the baseline, the state encoding is wrong and no amount of
network will save it.

    py -3.12 bc_probe.py [--winners-only] [--epochs 12]
"""
import argparse
import glob
import json
import os

import numpy as np

OPS = ["NORTH", "SOUTH", "EAST", "WEST", "PASS", "WATER", "HARVEST", "PLANT",
       "FEED", "CARE", "COLLECT_FERTILIZER", "DIG", "DROP", "PICKUP",
       "PLACE", "BUILD_COOP", "BUILD_PASTURE", "FERTILIZE"]
OP_IX = {o: i for i, o in enumerate(OPS)}
ME = "Joseph Paris"


def tile_feats(t):
    """What is standing on a tile, as a few numbers."""
    if t is None:
        return [1, 0, 0, 0, 0, 0, 0]
    if not isinstance(t, dict):
        return [0, 1, 0, 0, 0, 0, 0]           # LOCKED
    kind = t.get("kind")
    if kind == "PLANT":
        return [0, 0, 1,
                float(t.get("yield_units", 0)),
                float(bool(t.get("watered_today"))),
                float(t.get("consecutive_unwatered", 0)), 0]
    if kind == "WEED":
        return [0, 0, 0, 0, 0, 0, 1]
    return [0, 0, 0,
            float(t.get("yield_units", 0)),
            float(bool(t.get("fed_today"))),
            float(bool(t.get("fertilizer_available"))),
            float(bool(t.get("animal")))]


def featurise(obs, seat, pos):
    """Per-unit features: where it stands, what is under and around it."""
    farm = obs["farms"][seat]
    tiles = farm["tiles"]
    x, y = pos
    f = [1.0, obs["day"] / 30.0, obs["hour"] / 24.0,
         min(farm["money"], 50000) / 50000.0,
         x / 10.0, y / 10.0,
         abs(x - 4.5) / 5.0, abs(y - 4.5) / 5.0]
    f += tile_feats(tiles[y][x])
    # the four neighbours, which is what a move decision turns on
    for dx, dy in ((0, -1), (0, 1), (1, 0), (-1, 0)):
        nx, ny = x + dx, y + dy
        f += tile_feats(tiles[ny][nx]) if 0 <= nx < 10 and 0 <= ny < 10 \
            else [0, 1, 0, 0, 0, 0, 0]
    return f


def load(paths, winners_only):
    X, Y = [], []
    for path in paths:
        with open(path) as fh:
            d = json.load(fh)
        names = [a.get("Name") for a in d.get("info", {}).get("Agents", [])]
        rewards = [s.get("reward") or 0 for s in d["steps"][-1]]
        seats = range(2)
        if winners_only:
            seats = [0 if rewards[0] > rewards[1] else 1]
        for step in d["steps"]:
            obs = step[0]["observation"]
            for seat in seats:
                act = step[seat].get("action")
                if not isinstance(act, dict):
                    continue
                farm = obs["farms"][seat]
                units = [farm["farmer"]] + list(farm.get("hands") or [])
                ops = [act.get("farmer")] + list(act.get("hands") or [])
                for pos, op in zip(units, ops):
                    if not op or op[0] not in OP_IX:
                        continue
                    X.append(featurise(obs, seat, pos))
                    Y.append(OP_IX[op[0]])
    return np.array(X, dtype=np.float32), np.array(Y, dtype=np.int64)


def train(X, Y, epochs, lr=0.5):
    n, d = X.shape
    k = len(OPS)
    W = np.zeros((d, k), dtype=np.float32)
    for ep in range(epochs):
        idx = np.random.permutation(n)
        for i in range(0, n, 4096):
            b = idx[i:i + 4096]
            xb, yb = X[b], Y[b]
            z = xb @ W
            z -= z.max(axis=1, keepdims=True)
            p = np.exp(z)
            p /= p.sum(axis=1, keepdims=True)
            p[np.arange(len(b)), yb] -= 1.0
            W -= lr * (xb.T @ p) / len(b)
    return W


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="replays")
    ap.add_argument("--winners-only", action="store_true")
    ap.add_argument("--epochs", type=int, default=12)
    args = ap.parse_args()

    paths = sorted(glob.glob(os.path.join(args.dir, "*-replay.json")))
    if not paths:
        print("no replays")
        return
    hold = max(1, len(paths) // 4)
    tr, te = paths[:-hold], paths[-hold:]
    print("%d replays: %d train, %d held out%s"
          % (len(paths), len(tr), len(te),
             " (winners only)" if args.winners_only else ""))

    Xtr, Ytr = load(tr, args.winners_only)
    Xte, Yte = load(te, args.winners_only)
    print("  %d train pairs, %d test pairs, %d features"
          % (len(Ytr), len(Yte), Xtr.shape[1]))

    counts = np.bincount(Ytr, minlength=len(OPS))
    major = counts.argmax()
    base = (Yte == major).mean()
    print("  majority class '%s' -> %.1f%% baseline" % (OPS[major], 100 * base))

    W = train(Xtr, Ytr, args.epochs)
    pred = (Xte @ W).argmax(axis=1)
    acc = (pred == Yte).mean()
    print("  linear model         -> %.1f%% on held-out replays" % (100 * acc))
    print("")
    top = np.argsort(-counts)[:6]
    print("  per-class recall on the ops that matter:")
    for c in top:
        m = Yte == c
        if m.sum():
            print("    %-20s %5.1f%%  (%d%% of moves)"
                  % (OPS[c], 100 * (pred[m] == c).mean(),
                     round(100 * counts[c] / counts.sum())))


if __name__ == "__main__":
    main()
