---
id: 01
title: "Baseline agent and local evaluation harness"
priority: P0
effort: M
status: done
---

## Result

**Baseline: 100% win rate over 20 games vs `starter`, median final balance
$6,024 against their $3,560.** 10/10 vs `pass`. No crashes. ~2s per game, so
batches of 50+ are cheap.

That is the number to beat. Anything that does not clear ~$6,000 median against
`starter` is a regression.

### The bug that made the first version worthless

The first baseline scored **0% and +$46 profit over 30 days** — it lost a game
to `pass`, an agent that does nothing. Two wrong guesses (shed access, then
market behaviour) cost more time than tracing it did. `debug_trace.py` showed
the whole failure in one screen:

- It planted 15 tiles by day 2. One farmer has 24 actions/day, and watering a
  tile costs an action plus the walk, so most went two days unwatered.
- **The entire farm was weeds by day 6.**
- It then parked on its one surviving plant and farmed that single tile for the
  remaining 24 days — standing on a plant always returns water-or-harvest, so
  the "go find another tile" branch could never fire.

Fixing it meant sizing the plot to the workforce (`TILES_PER_UNIT = 6`) and
picking targets by urgency rather than by whatever the unit happened to stand
on. Water outranks harvest because two missed days destroys a plant outright,
while a late harvest costs nothing.

**Lesson worth keeping: trace before theorising.** The visible symptom was
"barely profitable", which reads as a weak strategy and is actually a farm that
died on day 6.

## Problem

Nothing about this competition can be improved until it can be measured. A
single game is not a measurement: weed spawns, town shop unlocks and market
drift all carry randomness, so the same agent scores differently run to run.

## What exists

- `main.py` — a pure wheat-loop baseline. Every unit runs the same policy:
  carry produce to the shed if holding any, else harvest/water/plant where it
  stands, else walk to the nearest bare tile. Market orders keep a seed buffer
  and dump the shed each turn.
- `eval.py` — runs N games against a named opponent and reports win rate plus
  the spread of final balances. Refuses to count a crashed agent as a loss,
  because that would hide a bug as a strategy problem.

## Acceptance criteria

- [ ] `py -3.12 eval.py --games 20 --opponent starter` runs clean, no crashes
- [ ] Baseline win rate against `starter` recorded here, with median balance
- [ ] Same against `random` and `pass` — `pass` should be a near-100% win rate,
      and anything less means the agent is broken rather than weak
- [ ] One replay dumped and eyeballed, to confirm units are doing what the
      policy intends rather than thrashing between tiles
- [ ] Wall-clock per game recorded, so batch sizes can be chosen sensibly

## Notes

The baseline is deliberately unsophisticated. Its job is to be a floor and to
exercise every mechanic the real agent needs — planting, the water/harvest
cycle, carrying to the shed, selling — so that later work is a change to a
working system rather than a first draft.

Known weaknesses to leave alone for now, since they are other issues:

- Sells the entire shed every turn regardless of price (issue 10)
- Grows only wheat (issue 04)
- Never hires, never buys land, never keeps animals (issues 05, 06, 07)
- Ignores the opponent entirely (issue 09)
