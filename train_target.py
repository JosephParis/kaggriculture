"""Learn *where to send each unit*, not which key to press.

The op-prediction policy reached 91% accuracy against our own heuristic and
still banked $1. Accuracy was never the constraint -- the action space was. An
op like SOUTH encodes a destination that the cell a unit stands on does not
contain, so movement was directionally weak and units random-walked; and with
no seed channel, PLANT was not expressible and was proposed zero times in a
full game.

This predicts the **target cell** instead, which is what the router actually
chooses. A 10x10 spatial softmax expresses it exactly. Movement then follows
from the target rather than being learned, and what is left to learn is task
selection -- the decision actually worth improving.

Shape: a shared trunk over the board, computed once a turn, and a small head
run per unit with two extra planes telling it where that unit stands and how
far each cell is. Eleven cheap heads beat eleven trunk passes.

    py -3.12 train_target.py --data data/dagger/pool_t.npz --out weights/t.npz
"""
import argparse
import os
import time

import numpy as np

try:
    import jax
    import jax.numpy as jnp
    from jax import lax
except ImportError:                                    # pragma: no cover
    raise SystemExit("training needs jax; inference does not")

import nn_features as F

TRUNK = 48
HEAD = 16
BLOCKS = 3
BOARD = 10


def init_params(key, n_in=None):
    n_in = n_in or F.N_CH
    ks = jax.random.split(key, 12)

    def conv(k, shape, scale=None):
        fan_in = shape[0] * shape[1] * shape[2]
        s = scale if scale is not None else (2.0 / fan_in) ** 0.5
        return jax.random.normal(k, shape, dtype=jnp.float32) * s

    p = {"stem_w": conv(ks[0], (3, 3, n_in, TRUNK)),
         "stem_b": jnp.zeros((TRUNK,))}
    for i in range(BLOCKS):
        p["b%d_w1" % i] = conv(ks[1 + i], (3, 3, TRUNK, TRUNK))
        p["b%d_b1" % i] = jnp.zeros((TRUNK,))
        p["b%d_w2" % i] = conv(ks[5 + i], (3, 3, TRUNK, TRUNK))
        p["b%d_b2" % i] = jnp.zeros((TRUNK,))
    # Head sees the trunk plus two per-unit planes: where this unit is, and
    # how far every cell is from it. Distance is given rather than learned
    # because it is exact and the walk is the cost the router trades against.
    p["h_w1"] = conv(ks[9], (3, 3, TRUNK + 2, HEAD))
    p["h_b1"] = jnp.zeros((HEAD,))
    p["h_w2"] = conv(ks[10], (1, 1, HEAD, 1), scale=0.01)
    p["h_b2"] = jnp.zeros((1,))
    return p


def _conv(x, w, b, pad="SAME"):
    y = lax.conv_general_dilated(x, w, (1, 1), pad,
                                 dimension_numbers=("NCHW", "HWIO", "NCHW"))
    return y + b[None, :, None, None]


def trunk(p, boards):
    x = jnp.maximum(_conv(boards, p["stem_w"], p["stem_b"]), 0)
    for i in range(BLOCKS):
        h = jnp.maximum(_conv(x, p["b%d_w1" % i], p["b%d_b1" % i]), 0)
        h = _conv(h, p["b%d_w2" % i], p["b%d_b2" % i])
        x = jnp.maximum(x + h, 0)
    return x


def _unit_planes(ys, xs):
    """(B,2,10,10): a one-hot for the unit's cell and a distance ramp."""
    gy, gx = jnp.mgrid[0:BOARD, 0:BOARD]
    gy = gy[None].astype(jnp.float32)
    gx = gx[None].astype(jnp.float32)
    uy = ys[:, None, None].astype(jnp.float32)
    ux = xs[:, None, None].astype(jnp.float32)
    here = ((gy == uy) & (gx == ux)).astype(jnp.float32)
    dist = (jnp.abs(gy - uy) + jnp.abs(gx - ux)) / 18.0
    return jnp.stack([here, dist], axis=1)


def target_logits(p, boards, ys, xs):
    t = trunk(p, boards)
    t = jnp.concatenate([t, _unit_planes(ys, xs)], axis=1)
    h = jnp.maximum(_conv(t, p["h_w1"], p["h_b1"]), 0)
    z = _conv(h, p["h_w2"], p["h_b2"])
    return z.reshape(z.shape[0], BOARD * BOARD)


def loss_fn(p, boards, ys, xs, labels):
    z = target_logits(p, boards, ys, xs)
    z = z - jax.scipy.special.logsumexp(z, axis=1, keepdims=True)
    return -jnp.mean(z[jnp.arange(z.shape[0]), labels])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--epochs", type=int, default=6)
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--init", default=None,
                    help="warm start from these weights; retraining from "
                         "scratch every DAgger round is what made cost grow "
                         "quadratically for no extra information")
    args = ap.parse_args()

    d = np.load(args.data)
    Btr, Gtr, Ttr = d["Btr"], d["Gtr"], d["Ttr"]
    Bte, Gte, Tte = d["Bte"], d["Gte"], d["Tte"]
    print("train %d samples / %d boards | test %d" % (len(Ttr), len(Btr),
                                                      len(Tte)))

    # The unit's own cell is the commonest target, so that is the baseline to
    # beat -- a policy that never moves anyone would score it.
    stay = np.mean(Tte == (Gte[:, 1] * BOARD + Gte[:, 2]))
    print("baseline 'stay put' -> %.1f%%" % (100 * stay))

    p = init_params(jax.random.PRNGKey(0))
    if args.init and os.path.exists(args.init):
        z = np.load(args.init)
        if z["stem_w"].shape[2] == F.N_CH:
            p = {k: jnp.asarray(z[k]) for k in z.files}
            print("warm started from %s" % args.init)
        else:
            print("ignoring %s: %d channels, encoder makes %d"
                  % (args.init, z["stem_w"].shape[2], F.N_CH))
    print("params: %d" % sum(int(np.prod(v.shape)) for v in p.values()))
    m = {k: jnp.zeros_like(v) for k, v in p.items()}
    v = {k: jnp.zeros_like(x) for k, x in p.items()}

    @jax.jit
    def step(p, m, v, t, boards, ys, xs, labels):
        loss, g = jax.value_and_grad(loss_fn)(p, boards, ys, xs, labels)
        np_, nm, nv = {}, {}, {}
        for k in p:
            m2 = 0.9 * m[k] + 0.1 * g[k]
            v2 = 0.999 * v[k] + 0.001 * (g[k] ** 2)
            np_[k] = p[k] - args.lr * (m2 / (1 - 0.9 ** t)) / (
                jnp.sqrt(v2 / (1 - 0.999 ** t)) + 1e-8)
            nm[k], nv[k] = m2, v2
        return np_, nm, nv, loss

    def evaluate(p, B, G, T, cap=6000):
        n = min(len(T), cap)
        hit = 0
        for i in range(0, n, 512):
            g = G[i:i + 512]
            z = target_logits(p, jnp.asarray(B[g[:, 0]], dtype=jnp.float32),
                              jnp.asarray(g[:, 1]), jnp.asarray(g[:, 2]))
            hit += int((np.asarray(z).argmax(1) == T[i:i + 512]).sum())
        return hit / float(n)

    t = 0
    for ep in range(args.epochs):
        order = np.random.permutation(len(Ttr))
        t0, tot, nb = time.time(), 0.0, 0
        for i in range(0, len(order) - args.batch, args.batch):
            b = order[i:i + args.batch]
            g = Gtr[b]
            t += 1
            p, m, v, loss = step(
                p, m, v, t,
                jnp.asarray(Btr[g[:, 0]], dtype=jnp.float32),
                jnp.asarray(g[:, 1]), jnp.asarray(g[:, 2]),
                jnp.asarray(Ttr[b].astype(np.int32)))
            tot += float(loss)
            nb += 1
        print("  epoch %d  loss %.3f  target acc %.1f%%  (%.0fs)"
              % (ep + 1, tot / max(1, nb), 100 * evaluate(p, Bte, Gte, Tte),
                 time.time() - t0))

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    np.savez_compressed(args.out, **{k: np.asarray(x, dtype=np.float32)
                                     for k, x in p.items()})
    print("wrote %s" % args.out)


if __name__ == "__main__":
    main()
