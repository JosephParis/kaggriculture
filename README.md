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

## Strategy

[docs/STRATEGY.md](docs/STRATEGY.md) is the plan: what the market will absorb,
why labour is the thing to buy, and the four-phase season. The backlog in
[docs/issues/](docs/issues/README.md) is ordered to match it.

The environment source is installed locally, so the game's exact rules,
constants and price function are readable — see the strategy doc for the path.
Prefer reading it over probing the simulator.

## Environment

- Use **`py -3.12`**. The default `python` on this machine is a sandboxed
  Microsoft Store 3.9.13 and is too old for most Kaggle simulation environments.
- Use **`py -3.12 -m kaggle`** for the CLI. There is an older `kaggle.exe`
  under the Store Python 3.9, but it is version 1.7.4.5 and only understands
  the legacy `kaggle.json` username/key pair -- it fails outright on a modern
  `KGAT_` API token. Credentials live in `~/.kaggle/access_token`.

## Rules

- **Submissions are manual.** They are rate-limited and cannot be withdrawn,
  so nothing automated ever submits. Build and evaluate locally.
- **The account must be identity-verified before it can submit at all.**
  Without it `CreateSubmission` returns a bare `403 Forbidden`; only the
  response body says why (`IdentityVerificationRequired`). Auth, joining the
  competition and the file upload all succeed first, so the failure looks like
  a broken token and is not. Verify a phone number at kaggle.com/settings.
  A 403 here consumes nothing -- no submission is recorded.
- This repo is public. Kaggle permits public sharing; what it forbids is private
  sharing outside a team. The tradeoff accepted here is that competitors can
  read the agent while the competition is live.
