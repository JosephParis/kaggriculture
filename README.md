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

Read in this order:

- [docs/TRIED.md](docs/TRIED.md) — **start here.** Every experiment run
  against this agent and its result, so nothing gets re-tried. Also the
  testing rules, which are not obvious and have burned us.
- [docs/STRATEGY.md](docs/STRATEGY.md) — the economics: what the market
  absorbs, why labour is the thing to buy, what the town drains.
- [docs/issues/](docs/issues/README.md) — the backlog, ordered to match.

The environment source is installed locally, so the exact rules, constants
and price function are readable. Prefer reading it over probing.

## Environment

- Use **`py -3.12`**. The default `python` on this machine is a sandboxed
  Microsoft Store 3.9.13 and is too old for most Kaggle simulation environments.
- Use **`py -3.12 -m kaggle`** for the CLI. There is an older `kaggle.exe`
  under the Store Python 3.9, but it is version 1.7.4.5 and only understands
  the legacy `kaggle.json` username/key pair -- it fails outright on a modern
  `KGAT_` API token. Credentials live in `~/.kaggle/access_token`.

## Rules

- **Submissions run through `submit.py`, which refuses more often than it
  sends.** The manual-only rule was relaxed on 21 August; the pre-flight is
  what replaced the human. It checks that the file parses and exposes
  `agent()`, that it imports nothing outside the standard library (a submitted
  agent runs without this repo, so a stray `import main` passes locally and
  fails there), that it plays a full 720-turn game without crashing and banks
  something plausible, that p99 is well inside `actTimeout`, and that the
  daily allowance is not already spent.

  ```
  py -3.12 submit.py --dry-run          # checks only
  py -3.12 submit.py -m "what changed and the evidence"
  ```

  The allowance resets on the **UTC** day, not the local one -- counting
  locally reported "0 left" against a real 4 on the first run.
- **Submitting works, and the CLI is `py -3.12 -m kaggle`.** First successful
  submission 18 Aug 2026 (id 55590014). The daily allowance is 5.

  ```
  py -3.12 -m kaggle competitions submit -c kaggriculture -f main.py -m "..."
  py -3.12 -m kaggle competitions submissions kaggriculture
  ```

- **If `CreateSubmission` returns a bare `403 Forbidden`, retry before
  concluding anything.** It happened twice here, with the body reading
  `IdentityVerificationRequired` (Kaggle's Persona check, which is a
  different and stronger thing than phone verification). The next attempt
  succeeded from the same account and token, so the gate is not reliably
  applied and the error is not to be trusted at face value. A 403 records no
  submission and costs nothing against the daily limit -- auth, competition
  entry and the upload all succeed first, so it also presents as a broken
  token and is not one.
- This repo is public. Kaggle permits public sharing; what it forbids is private
  sharing outside a team. The tradeoff accepted here is that competitors can
  read the agent while the competition is live.
