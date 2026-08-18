---
id: 04
title: "Crop mix: melon for the premium slice"
priority: P0
effort: M
status: done
---

## Result

**Median $48,857 against `starter`**, from $28,442 — melon alone was worth about
$20,000 a game, the single largest change made to this agent.

Twenty tiles just outside the animal zone, two cycles a season.

## Why melon is worth twenty wheat tiles

From the source, not from probing:

- `window_start = (max_yield_day + 1) // 2 = 6`, and watering ages 6–10 adds one
  unit a day to a base of 1, hitting the `max_yield` cap of 6 at age 10.
- `first_yield_day` is also 10, so **it ripens the same day it maxes out**. Ages
  11 and 12 add nothing and only walk toward the decay that starts at 13.
- Outside the window a plant only needs water every other day to survive, so
  the real schedule is: water on planting, alternate days to age 6, then daily
  through the window.

That is 1 plant + 8 waters + 1 harvest = **10 actions for 6 melons**. At the
~$217 average the market pays for the first 100 units, ~$130 an action, against
wheat's ~$11.

## The shape of the market decides the acreage

Melon's `above_func` is `sq` with `above_target` 3.60, so the price falls with
the square of the glut, and the town center drains only one melon a day. The
first 100 units are worth $21,721; the first 200 are worth $26,527. Everything
past ~150 is essentially free to the opponent.

Swept, on paired seeds:

| melon tiles | median |
|---|---|
| 8 | $38,208 |
| 12 | $42,692 |
| 16 | $46,844 |
| **20** | **$50,558** |
| 26 | $36,804 |

The cliff at 26 is the price curve, not a bug: the second cycle harvests into a
market the first cycle already flattened, and those tiles would have earned
more as geese. In a traced game the melon price holds $200–270 until day 24 and
then falls to $34 as the second harvest lands.

Flock size had to come down from 18 coops to 12 to pay for the melon ground.

## What it took structurally

Tiles previously *were* wheat by definition. They now carry a zoned crop, with
`CROP_SPEC` holding seed cost, harvest age and watering window per crop, and
`_last_plant_day` per crop so nothing is planted that cannot ripen.

## Still open

- **Melon is a race and we do not watch the other runner.** Both farms are
  public, so whether the opponent is growing melon is observable and decides
  whether our second cycle is worth planting at all. That is issue 09.
- Capping melon planting earlier (`MELON_LAST_PLANT`) swept flat: 13 and 19 are
  within noise of each other, 9 is $8,000 worse. The knob exists for when
  opponent-awareness gives it something to key off.
