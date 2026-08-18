---
id: 07
title: "Livestock: the goose/egg/fertilizer engine"
priority: P0
effort: L
status: done
---

## Result

**Median $28,442 against `starter` over 12 games, 100% win rate** (theirs
$3,484), up from $14,724 for the wheat-only engine and $6,024 for the original
baseline. Turn cost p99 0.74ms against the 1s `actTimeout`.

Geese are what the strategy doc predicted: ~$140/day/tile against wheat's ~$16.
Two eggs a day, because `CARE` banks a bonus paid out on the next production,
plus one fertilizer — and the fertilizer starts the day *after* placement,
before the first egg, which is why the payback is about three days.

Settled shape: 18 coops on the tiles nearest the shed, wheat on the rest and
grown mainly as feed, two quadrants of land, a crew sized off both jobs.

## The four bugs that made geese look like a loss

First measurement of the goose engine was **$12,636 — worse than wheat alone**.
Every one of these was invisible from the score and obvious in a trace.

1. **Coop-building outranked feeding.** The rancher's "go fetch feed" branch was
   skipped whenever any setup task existed, so the crew built twelve empty
   coops while the flock starved. Geese: 4 on day 2, 3 on day 3, **0 on day 4**.
2. **Geese were bought on day 0** out of the opening bank — six birds, $1,800,
   leaving $108 and no wheat to feed them. Cash then sat under $400 for twenty
   days and the wheat engine never started.
3. **The feed reserve and the purchase test were the same quantity.** Wheat was
   sold down to exactly `n_geese * reserve` every turn, and the test for
   affording another bird asked whether there was wheat *above* that line. The
   flock could never grow past eight.
4. **The distance tiebreak had been dropped** from task selection during a
   refactor. Units re-targeted whichever equally-urgent tile came first in block
   order, so they oscillated: **72% of all unit-actions were movement.**

Number 4 was only found by tallying actions by type rather than reading the
policy. The score said "geese are marginal"; the tally said "the farm is a
walking simulator". Worth keeping as a habit: when a policy underperforms and
the trace looks sane, count what the actions were actually spent on.

## The economics that held up

- **Fertilizer is the best single action in the game.** One
  `COLLECT_FERTILIZER`, ~$80, available every day from every surviving animal
  whether or not it was fed.
- **Never `FERTILIZE`.** Confirmed from the source: the yield bonus is worth
  $25-42 against a $60-100 sale.
- **Growing feed beats buying it**, which was not the prediction. The strategy
  doc assumed buying wheat at ~$25 was trivially worth it against $140/day of
  goose. Swept, `FEED_BUY=0` wins by $3,200: bought wheat costs $25-45 against
  the ~$20 ours sells for, and it competes for the 100-item shed.

## What this did not settle

- **Self-play halves the score.** Two copies of this agent land at ~$18k each
  rather than $28k, because they crash each other's fertilizer and egg prices.
  The leaderboard is full of strong opponents, so $28k against `starter` is an
  upper bound, not an expectation. This is the case for issue 10 (sell timing)
  and for melon (issue 04) as a race.
- **Eggs still sit near the `max_held` cap** for much of the season, which is
  production thrown away every night. Harvest is losing to fertilizer
  collection and feeding for rancher actions.
- The flock stalls short of 18 in practice; birds still escape occasionally.
- Weeds run 5-13 tiles mid-season, unrecovered.
