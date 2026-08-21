"""Count what the agent throws away.

Strategy work has been the expensive way to find gains here and bug-hunting the
cheap one: a running balance that was never decremented, hiring that read no
bank, and 542-885 market orders a game spent selling animals the environment
refuses to buy. All three were invisible in the score.

This tallies the leaks that cost nothing to look for:

  * **no-op unit actions** -- the environment silently drops an action it
    cannot apply, and a dropped action is a unit's whole turn
  * **dropped market orders** -- anything past `maxMarketOrdersPerTurn`, or a
    SELL of something not in PRODUCTS, is discarded but still costs its slot
  * **shed overflow** -- items past the 100 cap are destroyed at end of day
  * **unsold inventory** -- produce still held at the buzzer scores zero
  * **weeds** -- a tile that died rather than being harvested

    py -3.12 audit_waste.py [--games 3] [--opponent starter]
"""
import argparse
import collections

import main

SELLABLE = {"WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG",
            "MILK", "WOOL", "FERTILIZER"}
MOVES = {"NORTH", "SOUTH", "EAST", "WEST"}
MAX_ORDERS = 10
SHED_CAP = 100


def main_cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=3)
    ap.add_argument("--opponent", default="starter")
    ap.add_argument("--seed", type=int, default=3000)
    args = ap.parse_args()
    from kaggle_environments import make

    tot = collections.Counter()
    for g in range(args.games):
        prev = {}
        state = {"last": None}

        def traced(obs):
            me = obs["farms"][obs["player"]]
            priv = obs.get("private") or {}
            # Compare the board against the previous turn to see whether the
            # actions we issued actually changed anything.
            last = state["last"]
            if last is not None:
                lobs, lact = last
                lme = lobs["farms"][lobs["player"]]
                units = [lme["farmer"]] + list(lme.get("hands") or [])
                ops = [lact["farmer"]] + list(lact.get("hands") or [])
                now_units = [me["farmer"]] + list(me.get("hands") or [])
                for i, (pos, op) in enumerate(zip(units, ops)):
                    if not op or not pos:
                        continue
                    tot["acts"] += 1
                    name = op[0]
                    if name == "PASS":
                        tot["pass"] += 1
                        continue
                    if name in MOVES:
                        moved = (i < len(now_units)
                                 and list(now_units[i]) != list(pos))
                        if not moved:
                            tot["move_blocked"] += 1
                        continue
                    x, y = pos
                    before = lme["tiles"][y][x]
                    after = me["tiles"][y][x]
                    if before == after:
                        tot["noop_%s" % name] += 1
                        tot["noop"] += 1

                orders = lact.get("market") or []
                if len(orders) > MAX_ORDERS:
                    tot["orders_over_cap"] += len(orders) - MAX_ORDERS
                for o in orders[:MAX_ORDERS]:
                    if o[0] == "SELL" and o[1] not in SELLABLE:
                        tot["orders_unsellable"] += 1

            shed = priv.get("shed") or {}
            held = sum(v for k, v in shed.items() if k in SELLABLE)
            if held > SHED_CAP:
                tot["shed_over"] += held - SHED_CAP
            tot["weeds"] = max(tot["weeds"],
                               sum(1 for r in me["tiles"] for t in r
                                   if isinstance(t, dict)
                                   and t.get("kind") == "WEED"))
            out = main.agent(obs)
            state["last"] = (obs, out)
            return out

        env = make("kaggriculture", configuration={"seed": args.seed + g},
                   debug=False)
        env.run([traced, args.opponent])

        final = env.steps[-1][0].observation
        priv = (final or {}).get("private") or {}
        shed = priv.get("shed") or {}
        tot["unsold_shed"] += sum(v for k, v in shed.items() if k in SELLABLE)
        for inv in (priv.get("inventories") or []):
            tot["unsold_carried"] += sum(v for k, v in (inv or {}).items()
                                         if k in SELLABLE)

    n = float(args.games)
    acts = max(1, tot["acts"])
    print("per game, over %d games vs %s" % (args.games, args.opponent))
    print("  unit-actions issued        %8.0f" % (tot["acts"] / n))
    print("  ...idle (PASS)             %8.0f   %5.1f%%"
          % (tot["pass"] / n, 100.0 * tot["pass"] / acts))
    print("  ...moves that did not move %8.0f   %5.1f%%"
          % (tot["move_blocked"] / n, 100.0 * tot["move_blocked"] / acts))
    print("  ...acts that changed 0     %8.0f   %5.1f%%"
          % (tot["noop"] / n, 100.0 * tot["noop"] / acts))
    for k, v in sorted(tot.items(), key=lambda kv: -kv[1]):
        if k.startswith("noop_") and v:
            print("       %-22s %6.0f" % (k[5:], v / n))
    print("  market orders over the cap %8.0f" % (tot["orders_over_cap"] / n))
    print("  market orders unsellable   %8.0f" % (tot["orders_unsellable"] / n))
    print("  shed overflow (destroyed)  %8.0f" % (tot["shed_over"] / n))
    print("  unsold in shed at the end  %8.0f" % (tot["unsold_shed"] / n))
    print("  unsold carried at the end  %8.0f" % (tot["unsold_carried"] / n))
    print("  weeds on the board (peak)  %8.0f" % tot["weeds"])


if __name__ == "__main__":
    main_cli()
