"""Score weights on a whole test split, not the first 6,000 rows of it.

train_target.py's `evaluate` caps at 6,000 samples, which is one or two games
at the head of the split -- so "target acc" moves with which games happen to
sit at that boundary. That is enough to explain a 58% -> 85% jump between two
runs with different episode counts, so measure it properly before believing
either number.
"""
import argparse
import sys

import numpy as np

sys.path.insert(0, r"C:\Users\joeyk\onedrive\apps\kaggriculture")
import jax.numpy as jnp                                       # noqa: E402
from train_target import target_logits                        # noqa: E402


def load_params(path):
    z = np.load(path)
    return {k: jnp.asarray(z[k]) for k in z.files}


def score(p, B, G, T, idx, batch=512):
    hit = 0
    for i in range(0, len(idx), batch):
        sel = idx[i:i + batch]
        g = G[sel]
        z = target_logits(p, jnp.asarray(B[g[:, 0]], dtype=jnp.float32),
                          jnp.asarray(g[:, 1]), jnp.asarray(g[:, 2]))
        hit += int((np.asarray(z).argmax(1) == T[sel]).sum())
    return hit / float(len(idx))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", nargs="+", required=True)
    ap.add_argument("--pool", required=True)
    ap.add_argument("--sample", type=int, default=60000)
    args = ap.parse_args()

    z = np.load(args.pool)
    Bte, Gte, Tte = z["Bte"], z["Gte"], z["Tte"]
    stay = float(np.mean(Tte == (Gte[:, 1] * 10 + Gte[:, 2])))
    print("%s: %d test samples, stay-put baseline %.1f%%"
          % (args.pool.split("\\")[-1], len(Tte), 100 * stay))

    rs = np.random.RandomState(0)
    n = min(args.sample, len(Tte))
    idx_rand = rs.choice(len(Tte), n, replace=False)
    idx_head = np.arange(min(6000, len(Tte)))

    for w in args.weights:
        p = load_params(w)
        a_head = score(p, Bte, Gte, Tte, idx_head)
        a_rand = score(p, Bte, Gte, Tte, idx_rand)
        print("  %-22s head-6000 %5.1f%%   random-%d %5.1f%%"
              % (w.split("\\")[-1], 100 * a_head, n, 100 * a_rand))


if __name__ == "__main__":
    main()
