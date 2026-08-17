# Kaggriculture

An autonomous agent for [Kaggle's Kaggriculture competition](https://www.kaggle.com/competitions/kaggriculture).

**Deadline: 30 September 2026.** $50,000 pool, $5,000 to each of the top 10.

## What the competition actually is

Not a tabular ML problem. The agent runs a farm across a 30-day simulated
season, making hundreds of real-time decisions — planting and harvesting,
livestock, hiring labour, expanding land, and trading in a market whose prices
move with supply and demand. Scored on income.

So this is a policy and simulation problem, not a feature-engineering one. A
gradient-boosted model over a feature table is the wrong shape.

## Environment

- Use **`py -3.12`**. The default `python` on this machine is a sandboxed
  Microsoft Store 3.9.13 and is too old for most Kaggle simulation environments.
- The `kaggle` CLI is installed but not on `PATH`:
  `%LOCALAPPDATA%\Packages\PythonSoftwareFoundation.Python.3.9_qbz5n2kfra8p0\LocalCache\local-packages\Python39\Scripts\kaggle.exe`

## Rules

- **Submissions are manual.** They are rate-limited and cannot be withdrawn, so
  nothing automated ever submits. Build and evaluate locally.
- This repo is public. Kaggle permits public sharing; what it forbids is private
  sharing outside a team. The tradeoff accepted here is that competitors can
  read the agent while the competition is live.
