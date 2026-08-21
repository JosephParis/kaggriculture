"""Run the cloned policy with numpy alone.

Training uses JAX; this does not. A submitted agent runs on a machine whose
package set is not ours to choose, and betting a submission slot on JAX or
PyTorch being importable there is a bad trade when the forward pass is forty
lines of numpy. numpy itself is safe -- `kaggle_environments` depends on it.

The network is small on purpose: 48 channels, three residual blocks, a 10x10
board. One forward pass a turn serves every unit, since each reads the cell it
stands on. Budget is 1000ms a turn and the heuristic already uses 1.3ms.

    from nn_policy import Policy
    pol = Policy("weights/bc.npz")
    logits = pol.cell_logits(planes)        # (N_OPS, 10, 10)
"""
import os

import numpy as np

import nn_features as F


def _conv3(x, w, b):
    """3x3 'SAME' convolution. x (C,H,W), w (3,3,Cin,Cout) -> (Cout,H,W)."""
    cin, h, wd = x.shape
    pad = np.zeros((cin, h + 2, wd + 2), dtype=np.float32)
    pad[:, 1:-1, 1:-1] = x
    # Sum the nine shifted products; at this size an explicit loop beats
    # building an im2col matrix and is far easier to read.
    out = np.zeros((w.shape[3], h, wd), dtype=np.float32)
    for dy in range(3):
        for dx in range(3):
            patch = pad[:, dy:dy + h, dx:dx + wd]          # (Cin,H,W)
            out += np.tensordot(w[dy, dx], patch, axes=([0], [0]))
    return out + b[:, None, None]


def _conv1(x, w, b):
    return np.tensordot(w[0, 0], x, axes=([0], [0])) + b[:, None, None]


class Policy(object):
    """Per-cell action logits from a board encoding."""

    def __init__(self, path):
        z = np.load(path)
        self.p = {k: np.asarray(z[k], dtype=np.float32) for k in z.files}
        self.blocks = 0
        while ("b%d_w1" % self.blocks) in self.p:
            self.blocks += 1

    @staticmethod
    def available(path):
        return os.path.exists(path)

    def cell_logits(self, planes):
        p = self.p
        x = _conv3(planes, p["stem_w"], p["stem_b"])
        np.maximum(x, 0, out=x)
        for i in range(self.blocks):
            h = _conv3(x, p["b%d_w1" % i], p["b%d_b1" % i])
            np.maximum(h, 0, out=h)
            h = _conv3(h, p["b%d_w2" % i], p["b%d_b2" % i])
            x = x + h
            np.maximum(x, 0, out=x)
        return _conv1(x, p["head_w"], p["head_b"])

    def unit_scores(self, cell, x, y, carrying=0.0):
        """Logits for the unit standing at (x, y)."""
        got = cell[:, y, x]
        if "carry_w" in self.p:
            got = got + float(carrying) * self.p["carry_w"][0]
        return got

    def rank(self, cell, x, y, carrying=0.0):
        """Ops for one unit, best first, as (op_name, score)."""
        s = self.unit_scores(cell, x, y, carrying)
        return [(F.OPS[i], float(s[i])) for i in np.argsort(-s)]


class TargetPolicy(object):
    """Scores every cell as a destination for one unit.

    The op-head policy could not express "walk five tiles to that melon", so
    it wandered. This scores targets instead, which is what the router
    actually chooses, and the agent only ever offers it cells that already
    have work -- so a bad score costs a worse job, never a wasted turn.
    """

    def __init__(self, path):
        z = np.load(path)
        self.p = {k: np.asarray(z[k], dtype=np.float32) for k in z.files}
        self.blocks = 0
        while ("b%d_w1" % self.blocks) in self.p:
            self.blocks += 1
        gy, gx = np.mgrid[0:10, 0:10]
        self._gy = gy.astype(np.float32)
        self._gx = gx.astype(np.float32)

    @staticmethod
    def available(path):
        return os.path.exists(path)

    def trunk(self, planes):
        p = self.p
        x = _conv3(planes, p["stem_w"], p["stem_b"])
        np.maximum(x, 0, out=x)
        for i in range(self.blocks):
            h = _conv3(x, p["b%d_w1" % i], p["b%d_b1" % i])
            np.maximum(h, 0, out=h)
            h = _conv3(h, p["b%d_w2" % i], p["b%d_b2" % i])
            x = x + h
            np.maximum(x, 0, out=x)
        return x

    def scores(self, trunk, ux, uy):
        """(10,10) destination scores for the unit standing at (ux, uy)."""
        here = ((self._gy == uy) & (self._gx == ux)).astype(np.float32)
        dist = (np.abs(self._gy - uy) + np.abs(self._gx - ux)) / 18.0
        x = np.concatenate([trunk, here[None], dist[None]], axis=0)
        h = _conv3(x, self.p["h_w1"], self.p["h_b1"])
        np.maximum(h, 0, out=h)
        return _conv1(h, self.p["h_w2"], self.p["h_b2"])[0]
