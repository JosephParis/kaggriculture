"""DAgger: train the policy on the states it actually visits.

Cloning from replays gives a policy that is 65% accurate on expert states and
banks $1 when it drives. The gap is distribution shift -- once it errs it is
in board states no demonstration contained, and it has never been told what to
do there.

DAgger closes that by iterating: let the policy drive, record the states it
reaches, label them with an expert, aggregate, retrain. Two things make it
unusually cheap here.

  * **The expert is free and exact.** `main.py`'s heuristic computes its own op
    for every unit before the policy overrides it, so the label is already
    sitting there. No human, no search, no separate oracle.
  * **The data is unlimited.** Rollouts run at ~227 episodes/min across the
    box, against a fixed replay corpus of 32 games.

    py -3.12 dagger.py --iters 3 --games 6

Each iteration reports the thing that actually matters: the bank the policy
posts when it drives unaided. Cloning starts that at $1.
"""
import argparse
import json
import os
import subprocess
import sys
import time

import numpy as np

WORK = "data/dagger"


def rollout_worker():
    """Play games with the policy driving, dumping expert labels."""
    import main
    from kaggle_environments import make
    games = int(os.environ["DG_GAMES"])
    seed = int(os.environ["DG_SEED"])
    out = os.environ["DG_OUT"]

    boards, gather, labels, carry, targets = [], [], [], [], []
    banks = []
    import nn_features as F
    for g in range(games):
        main.DAGGER_LOG[:] = []
        env = make("kaggriculture", configuration={"seed": seed + g},
                   debug=False)
        env.run([main.agent, "starter"])
        banks.append(float(env.steps[-1][0].reward or 0))
        for planes, experts in main.DAGGER_LOG:
            bi = len(boards)
            boards.append(np.asarray(planes, dtype=np.float16))
            for rec in experts:
                y, x, op, carried, ty, tx = rec
                if not op or op[0] not in F.OP_IX:
                    continue
                gather.append((bi, y, x))
                labels.append(F.OP_IX[op[0]])
                carry.append(carried)
                targets.append(ty * 10 + tx)      # the cell it was sent to
    np.savez_compressed(out,
                        B=np.asarray(boards, dtype=np.float16),
                        G=np.asarray(gather, dtype=np.int32),
                        Y=np.asarray(labels, dtype=np.int8),
                        C=np.asarray(carry, dtype=np.float16),
                        T=np.asarray(targets, dtype=np.int16),
                        banks=np.asarray(banks, dtype=np.float32))
    print(json.dumps({"banks": banks}))


def collect(weights, beta, games, seed, workers, drive):
    """Run rollouts in parallel and merge what they captured."""
    os.makedirs(WORK, exist_ok=True)
    procs, outs = [], []
    per = max(1, games // workers)
    for w in range(workers):
        out = os.path.join(WORK, "shard%d.npz" % w)
        outs.append(out)
        env = dict(os.environ)
        env.update({"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
                    "PYTHONPATH": ".",
                    "KAG_DAGGER_CAPTURE": "1",
                    "KAG_LEARNED_UNITS": str(drive),
                    "KAG_DAGGER_BETA": str(beta),
                    "KAG_WEIGHTS": weights or "weights/none.npz",
                    "DG_GAMES": str(per), "DG_SEED": str(seed + w * 100),
                    "DG_OUT": out})
        procs.append(subprocess.Popen(
            [sys.executable, "dagger.py", "--worker"],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True))
    banks = []
    for p in procs:
        so, _ = p.communicate(timeout=7200)
        for line in (so or "").splitlines():
            if line.startswith("{"):
                banks += json.loads(line)["banks"]

    B, G, Y, C, T = [], [], [], [], []
    base = 0
    for out in outs:
        if not os.path.exists(out):
            continue
        # np.load keeps the archive open, and on Windows an open handle
        # blocks the delete -- so copy out and close before removing.
        with np.load(out) as d:
            if not len(d["Y"]):
                continue
            g = d["G"].copy()
            g[:, 0] += base
            B.append(d["B"].copy())
            G.append(g)
            Y.append(d["Y"].copy())
            C.append(d["C"].copy())
            T.append(d["T"].copy())
            base += len(d["B"])
        os.remove(out)
    if not B:
        return None, banks
    return (np.concatenate(B), np.concatenate(G), np.concatenate(Y),
            np.concatenate(C), np.concatenate(T)), banks


def main_cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", action="store_true")
    ap.add_argument("--iters", type=int, default=3)
    ap.add_argument("--games", type=int, default=6)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--seed", type=int, default=7000)
    args = ap.parse_args()

    if args.worker:
        rollout_worker()
        return

    os.makedirs("weights", exist_ok=True)
    os.makedirs(WORK, exist_ok=True)
    pool = None
    weights = None

    for it in range(args.iters):
        # Iteration 0 has no policy, so the expert drives and we collect its
        # own states -- ordinary cloning. After that beta decays and the
        # policy's own states take over, which is the entire point.
        beta = 1.0 if it == 0 else max(0.0, 0.5 ** it)
        drive = 0 if it == 0 else 2
        t0 = time.time()
        got, banks = collect(weights, beta, args.games, args.seed + it * 1000,
                             args.workers, drive)
        if got is None:
            print("iteration %d collected nothing" % it)
            break
        med = float(np.median(banks)) if banks else 0.0
        print("iter %d  beta %.2f  drive %d  %d games  median bank $%s  (%.0fs)"
              % (it, beta, drive, len(banks), format(int(med), ","),
                 time.time() - t0))

        if pool is None:
            pool = got
        else:
            g = got[1].copy()
            g[:, 0] += len(pool[0])
            pool = (np.concatenate([pool[0], got[0]]),
                    np.concatenate([pool[1], g]),
                    np.concatenate([pool[2], got[2]]),
                    np.concatenate([pool[3], got[3]]),
                    np.concatenate([pool[4], got[4]]))
        print("   pool: %d boards, %d labelled actions"
              % (len(pool[0]), len(pool[2])))

        # Hold out the last tenth of boards so accuracy is not self-reported
        # on states the net just trained on.
        nb = len(pool[0])
        cut = int(nb * 0.9)
        mtr, mte = pool[1][:, 0] < cut, pool[1][:, 0] >= cut
        data = os.path.join(WORK, "pool.npz")
        np.savez_compressed(
            data,
            Btr=pool[0], Gtr=pool[1][mtr], Ytr=pool[2][mtr], Ctr=pool[3][mtr],
            Ttr=pool[4][mtr], Mtr=np.zeros((1, 2), dtype=np.float32),
            Bte=pool[0], Gte=pool[1][mte], Yte=pool[2][mte], Cte=pool[3][mte],
            Tte=pool[4][mte], Mte=np.zeros((1, 2), dtype=np.float32))

        weights = "weights/dagger%d.npz" % it
        subprocess.run(
            [sys.executable, "train_target.py", "--data", data,
             "--out", weights, "--epochs", str(args.epochs)],
            env=dict(os.environ, PYTHONPATH="."), check=True)

    print("")
    print("final weights: %s" % weights)
    print("evaluate with:")
    print("  KAG_LEARNED_UNITS=2 KAG_WEIGHTS=%s py -3.12 eval.py --games 6"
          % weights)


if __name__ == "__main__":
    main_cli()
