---
id: 02
title: "Measure the price function empirically"
priority: P0
effort: M
status: closed
---

## Resolution — closed 17 August 2026, without probing

The environment source is installed on this machine:

    kaggle_environments/envs/kaggriculture/kaggriculture.py

`MARKET_PARAMS` and `market_price()` are the price function, exactly. There was
never a curve to recover. The tabulated answers now live in
[../STRATEGY.md](../STRATEGY.md); the short version:

- **Wheat never crashes.** Its `above_func` is `log`: ~$23/unit at 50 sold,
  ~$21 at 200, ~$20 at 800. The question this issue was written to answer —
  "how many wheat per day before the marginal unit stops paying for its
  labour?" — has the answer **effectively none, at any volume we can reach**.
  Wheat is a flat ~$20 sink. Egg behaves the same way at ~$40.
- **Volume is not the binding constraint; labour is.** So the "grow more"
  instinct is right, and the real question is how many actions we can buy.
- The premium goods are the exception and invert the logic: strawberry, milk
  and wool hit the $1 floor by unit ~50, and melon by ~150. Those are a race
  against the opponent, not a production problem.
- Recovery is driven by town consumption, which drains inventory every turn.
  Wheat is demanded by 5 of 8 shop types and egg by 2, so both recover and rise
  late in the season. **Fertilizer is demanded by nothing and never recovers.**

Lesson worth keeping: check whether the answer is already sitting in an
installed package before designing an experiment to measure it.

## Problem

The README describes prices as moving with market inventory: base price at the
shared starting inventory `I0`, rising as inventory falls, falling as it grows,
with a per-resource shape (`linear`, `sq`, `sqrt`, `log`) that can differ either
side of `I0`. Premium goods are said to collapse toward the $1 floor on a glut
while staples absorb supply more gently.

That is qualitative. Every production decision needs the actual numbers.

**The question that matters: how many units of wheat can be sold per day before
the marginal unit is worth less than the labour that produced it?** If the
answer is small, then out-producing the opponent is the wrong strategy and the
game is about crop mix and timing instead.

## Why this is P0

It determines whether the whole "grow more" instinct is right. It is cheap to
answer — a scripted agent that sells a fixed quantity per day and logs the
resulting price curve — and every later decision depends on it.

It also has a competitive edge: the market is **shared**. The opponent's selling
moves your prices. A glut caused by them is indistinguishable from one caused by
you, and both have to be planned around.

## Approach

- Write a probe agent that does nothing but sell a fixed number of units per
  day, holding everything else constant
- Sweep that quantity across runs; log `market.prices` and `market.inventory`
  every turn
- Recover the curve per product: where is `I0`, what is the shape either side,
  how fast does recovery happen when selling stops
- Repeat for at least wheat, melon, and one animal product — the README claims
  they behave differently, and that claim is the whole point

## Acceptance criteria

- [ ] Price-vs-inventory curve plotted or tabulated for wheat, melon, milk
- [ ] The daily sale volume at which wheat drops below ~50% of base, stated as a
      number
- [ ] Recovery rate measured: turns for a glutted price to return to base once
      selling stops
- [ ] A short written conclusion on whether volume or price is the binding
      constraint, recorded here, since issues 04 and 10 both depend on the answer
- [ ] Findings summarised in `docs/issues/README.md` so later work does not
      re-derive them
