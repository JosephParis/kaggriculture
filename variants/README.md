# Variants

Submitted agents that differ from `main.py`, and the sparring partners used to
judge them. Each is a full standalone agent: the only differences are the
`_P()` policy constants at the top.

## Submitted

| file | change from `main.py` | local h2h vs `main.py` |
|---|---|---|
| `v4-herd-8c5s.py` | 8 cows / **5** sheep | 10-14 (−4) |
| `v5-melon-cutoff-13.py` | melon planting stops day 13 | 7-7-10 (tied) |

Both sit at or near parity in the mirror and differ structurally, which is the
point: every local comparison here is a **mirror match**, and a mirror is not
the ladder. When both sides run the same build they dump the same premium
goods on the same turn, so mirror results systematically punish anything that
leans on a market the field may not be contesting.

## Sparring partners

`spar_cow.py` (12 cows, no melon), `spar_melon.py` (melon IPO: 24 melon, 2
cows) and `spar_v3.py` (our incumbent) stand in for the clusters the public
notebooks describe. Use them with `panel.py`:

```
py -3.12 panel.py cand.py --panel starter spar_cow.py spar_melon.py spar_v3.py
```

In practice only `spar_v3` discriminates — everything beats the simple clusters
12-0 — so `h2h.py` against the incumbent is usually the faster signal.

**Sample size matters more than it looks.** A 6-game panel run rated a
melon-20 build level with the incumbent; the same comparison over 28 games had
it losing 2-26. Use at least 12 games a seat before believing a margin.
