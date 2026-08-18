---
id: 13
title: "Parameter sweep harness over batched games"
priority: P0
effort: M
status: done
---

## Result

`sweep.py` runs a cross product of `KAG_*` overrides, every configuration
against **the same seeds**, in parallel subprocesses, and ranks by median final
balance.

```
py -3.12 sweep.py GOOSE_TARGET=16,18,22 FEED_BUY=0,1 --games 12 --seed 5000
```

`main.py` reads every policy constant through `_P(name, default)`, so a knob
becomes sweepable by being named, and the defaults are what gets submitted.
`eval.py` grew `--json` to feed it.

## Why paired seeds turned out to be the whole point

The first comparison run in this repo was 4 unseeded games, and it said the
distance tiebreak in task selection was a **$3,400 regression**. Re-run as 10
paired games, the same change was a **$3,600 improvement**. The unpaired
batch had the sign backwards.

Weed spawns, shop draws and the opponent's market pressure swamp differences of
a few thousand dollars. Anything compared on unpaired games below ~30 is
guessing.

**Lesson worth keeping: never compare two policies on different games.** The
repo rule was already "never report a single game"; the sharper version is that
batch size does not rescue an unpaired comparison, and pairing makes small
batches usable.

## What it found

| Knob | Swept | Chosen | Margin |
|---|---|---|---|
| `MAX_LAND` | 0,1,2,3 | **2** | $12,502 vs $9,405 for 3 |
| `TILES_PER_UNIT` | 4,5,6,8,10 | **8** | ~$1,700 over 7 and 9 |
| `GOOSE_TARGET` | 8..30 | **18** | collapses to $5,680 at 30 |
| `FEED_BUY` | 0,1 | **0** | $28,564 vs $25,393 |
| `TIEBREAK_DIST` | 0,1 | **1** | $21,824 vs $18,206 |

The two structural findings, both of which the sweep surfaced before anyone
reasoned them out:

- **The third quadrant never pays.** $4,000 comes straight off the final score
  and 25 tiles cannot earn it back in the days remaining.
- **Large flocks fall off a cliff, not a slope.** Past ~24 geese the score
  drops by two thirds, because the animal zone eats the tiles and the ranchers
  eat the crew. A knob that is fine at 18 and catastrophic at 24 is not
  something to find by intuition.

## Notes

Configurations run as subprocesses with `OMP_NUM_THREADS=1` and friends:
`kaggle_environments` pulls in numpy/OpenBLAS, which allocates a thread pool per
process and exhausts memory once several games run side by side.

Still open: the sweep is a grid, so it only ever finds axis-aligned optima and
costs one full batch per point. With ~4s a game and knobs interacting (flock
size against crew size against land), a coordinate-descent or random-search
mode would cover more ground for the same wall clock.
