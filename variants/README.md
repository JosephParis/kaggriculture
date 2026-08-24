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

## Rejected, kept for re-running

| file | change from `main.py` | local h2h vs `main.py` |
|---|---|---|
| `priced-routing.py` | `PRICED_ROUTING=1`: rank tasks by `value / (dist + 1)` | **4-20-0** |
| `priced-routing-v2.py` | the same, with `T_RESCUE` kept absolute and `DIG` unpriced past the planting cutoff | **4-20-0** |

Both bank *more* against `starter` than the incumbent and lose decisively in
the mirror. See TRIED.md, "Routing". Kept so the result can be re-run rather
than re-derived.

## Sell timing (issue 10)

| file | change from `main.py` | local h2h vs `main.py` |
|---|---|---|
| `sell-meter.py` | `SELL_METER=1`: premium goods sold a slice a turn | **8-16-0** |
| `melon-switch.py` | `MELON_SWITCH=1` at threshold 180: melon ground replanted as strawberry once melon dies | **2-22-0** |

Both are market-aware and both lose, for opposite reasons: there is no glut to
meter and holding stock loses the race for town demand, while the one good that
does crash is the one we cannot afford to stop growing. See TRIED.md, "Sell
timing and the market".

`sell-meter.py` is also a worked example of why the bank is only a filter: its
bank is within noise of the incumbent's and it still loses two games in three.

## Ported from the 804-rated ladder submission (20 August)

| file | change from `main.py` | result |
|---|---|---|
| `land-day6.py` | `LAND_START_DAY=6`: buy land on day 6, as the 804 build does | +$464 bank, **6-18-0** |

The only piece of that build worth a variant, and it still loses. See
TRIED.md, "Reconciling this repo with the ladder submissions".

## Accepted

| file | change | result |
|---|---|---|
| `wheat-block.py` | strawberry 44 → 34, the freed tiles fall back to wheat | **21-3-0**, now the default in `main.py` |
| `wheat-block-28.py` | the same at 28 tiles | 19-5-0, slightly better bank, worse h2h |

Found by diffing ten real losses, not by sweeping. See TRIED.md, "What the
replays actually said".

## Portfolio (20 August)

| file | change from `main.py` | result |
|---|---|---|
| `portfolio.py` | 12 geese / 3 cows / 2 sheep, melon 6, strawberry 13, rest wheat | **0-24-0** |

The allocation `allocate.py` recommended. It loses every game, which is what
retired the allocator -- see TRIED.md, "Solving the whole allocation at once".

## Crew and land (20 August)

| file | change from `main.py` | result |
|---|---|---|
| `hire-to-work.py` | `HIRE_TO_WORK=1`: crew sized off work and cash, not tiles owned | worse, $94.2k vs $100.9k |
| `land-3.py` | `MAX_LAND=3`: buy the fourth quadrant | **0-24** mirror; 12W-0L either way vs recorded farms |
| `carrot-block.py` | strawberry 40 -> 34, and the freed block sown with carrot (`CARROT_TILES=10`) | **0-24** and **1-23** on two seed sets; **4-20** against the same block sown with wheat |
| `wheat-block-restored.py` | strawberry 40 -> 34, restoring the wheat block ghost tuning reverted | **5-19** vs `main.py` |

`land-3.py` is the interesting failure. It banks more than the incumbent
against `starter` and against two of the three recorded farms, and it still
does not qualify: every recorded farm loses 12-0 to *both* builds, so the
bank margin buys no rating, and the mirror says 0-24.

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
