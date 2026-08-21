"""Clone the experts: train the unit-control policy on replay data.

A small residual CNN over the 10x10 board produces per-cell action logits, and
each unit reads the cell it stands on. Parameters are a plain dict of arrays
rather than a framework's module tree, because the policy has to run inside a
submitted agent as **numpy only** -- exporting a dict is a one-liner, and
exporting a framework checkpoint is a project.

    py -3.12 train_bc.py --epochs 8 --out weights/bc.npz

Reports held-out accuracy against the majority-class baseline. Held out by
*replay*, so it never scores itself on a game it trained on.
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

CH = 48          # residual width; small enough to run in numpy in ~1ms
BLOCKS = 3


def init_params(key, n_in=F.N_CH, n_out=F.N_OPS):
    ks = jax.random.split(key, 10)
    p = {}

    def conv(k, shape, scale=None):
        fan_in = shape[0] * shape[1] * shape[2]
        s = scale if scale is not None else (2.0 / fan_in) ** 0.5
        return jax.random.normal(k, shape, dtype=jnp.float32) * s

    p["stem_w"] = conv(ks[0], (3, 3, n_in, CH))
    p["stem_b"] = jnp.zeros((CH,))
    for i in range(BLOCKS):
        p["b%d_w1" % i] = conv(ks[1 + i], (3, 3, CH, CH))
        p["b%d_b1" % i] = jnp.zeros((CH,))
        p["b%d_w2" % i] = conv(ks[4 + i], (3, 3, CH, CH))
        p["b%d_b2" % i] = jnp.zeros((CH,))
    p["head_w"] = conv(ks[7], (1, 1, CH, n_out), scale=0.01)
    p["head_b"] = jnp.zeros((n_out,))
    # Carrying is per-unit, not per-cell, so it enters at the gather instead
    # of as a plane -- a DROP decision turns on it and nothing else does.
    p["carry_w"] = jnp.zeros((1, n_out))
    return p


def _conv(x, w, b):
    y = lax.conv_general_dilated(
        x, w, (1, 1), "SAME",
        dimension_numbers=("NCHW", "HWIO", "NCHW"))
    return y + b[None, :, None, None]


def forward(p, boards):
    """boards (B, C, 10, 10) -> per-cell logits (B, N_OPS, 10, 10)."""
    x = jnp.maximum(_conv(boards, p["stem_w"], p["stem_b"]), 0)
    for i in range(BLOCKS):
        h = jnp.maximum(_conv(x, p["b%d_w1" % i], p["b%d_b1" % i]), 0)
        h = _conv(h, p["b%d_w2" % i], p["b%d_b2" % i])
        x = jnp.maximum(x + h, 0)
    return _conv(x, p["head_w"], p["head_b"])


def unit_logits(p, boards, ys, xs, carry):
    cell = forward(p, boards)                       # (B, OPS, 10, 10)
    n = jnp.arange(cell.shape[0])
    got = cell[n, :, ys, xs]                        # (B, OPS)
    return got + carry[:, None] * p["carry_w"]


def loss_fn(p, boards, ys, xs, carry, labels):
    z = unit_logits(p, boards, ys, xs, carry)
    z = z - jax.scipy.special.logsumexp(z, axis=1, keepdims=True)
    return -jnp.mean(z[jnp.arange(z.shape[0]), labels])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/bc.npz")
    ap.add_argument("--out", default="weights/bc.npz")
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--lr", type=float, default=2e-3)
    args = ap.parse_args()

    d = np.load(args.data)
    Btr, Gtr, Ytr, Ctr = d["Btr"], d["Gtr"], d["Ytr"], d["Ctr"]
    Bte, Gte, Yte, Cte = d["Bte"], d["Gte"], d["Yte"], d["Cte"]
    print("train %d samples over %d boards | test %d over %d"
          % (len(Ytr), len(Btr), len(Yte), len(Bte)))

    counts = np.bincount(Ytr.astype(int), minlength=F.N_OPS)
    base = (Yte.astype(int) == counts.argmax()).mean()
    print("majority class '%s' -> %.1f%% baseline"
          % (F.OPS[counts.argmax()], 100 * base))

    key = jax.random.PRNGKey(0)
    p = init_params(key)
    nparam = sum(int(np.prod(v.shape)) for v in p.values())
    print("policy: %d params, %d channels, %d blocks" % (nparam, CH, BLOCKS))

    m = {k: jnp.zeros_like(v) for k, v in p.items()}
    v = {k: jnp.zeros_like(x) for k, x in p.items()}
    grad_fn = jax.jit(jax.value_and_grad(loss_fn))

    @jax.jit
    def step(p, m, v, t, boards, ys, xs, carry, labels):
        loss, g = jax.value_and_grad(loss_fn)(p, boards, ys, xs, carry, labels)
        out_p, out_m, out_v = {}, {}, {}
        for k in p:
            m2 = 0.9 * m[k] + 0.1 * g[k]
            v2 = 0.999 * v[k] + 0.001 * (g[k] ** 2)
            mhat = m2 / (1 - 0.9 ** t)
            vhat = v2 / (1 - 0.999 ** t)
            out_p[k] = p[k] - args.lr * mhat / (jnp.sqrt(vhat) + 1e-8)
            out_m[k], out_v[k] = m2, v2
        return out_p, out_m, out_v, loss

    def evaluate(p, B, G, Y, C, cap=8000):
        n = min(len(Y), cap)
        acc = 0
        for i in range(0, n, 1024):
            g = G[i:i + 1024]
            z = unit_logits(p, jnp.asarray(B[g[:, 0]], dtype=jnp.float32),
                            jnp.asarray(g[:, 1]), jnp.asarray(g[:, 2]),
                            jnp.asarray(C[i:i + 1024], dtype=jnp.float32))
            acc += int((np.asarray(z).argmax(1) == Y[i:i + 1024]).sum())
        return acc / float(n)

    t = 0
    for ep in range(args.epochs):
        order = np.random.permutation(len(Ytr))
        t0, tot, nb = time.time(), 0.0, 0
        for i in range(0, len(order) - args.batch, args.batch):
            b = order[i:i + args.batch]
            g = Gtr[b]
            t += 1
            p, m, v, loss = step(
                p, m, v, t,
                jnp.asarray(Btr[g[:, 0]], dtype=jnp.float32),
                jnp.asarray(g[:, 1]), jnp.asarray(g[:, 2]),
                jnp.asarray(Ctr[b], dtype=jnp.float32),
                jnp.asarray(Ytr[b].astype(np.int32)))
            tot += float(loss)
            nb += 1
        acc = evaluate(p, Bte, Gte, Yte, Cte)
        print("  epoch %d  loss %.3f  held-out %.1f%%  (%.0fs)"
              % (ep + 1, tot / max(1, nb), 100 * acc, time.time() - t0))

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    np.savez_compressed(args.out,
                        **{k: np.asarray(x, dtype=np.float32)
                           for k, x in p.items()})
    print("wrote %s (%.1f MB)"
          % (args.out, os.path.getsize(args.out) / 1e6))


if __name__ == "__main__":
    main()
