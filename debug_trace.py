"""
Trace one game and print what the agent is actually doing.

Guessing at why a baseline underperforms wastes more time than looking. This
dumps the observable state at intervals so the failure mode is visible rather
than inferred.
"""
import sys
from kaggle_environments import make

env = make("kaggriculture", debug=True)
env.run(["main.py", "pass"])

print(f"\ntotal steps recorded: {len(env.steps)}\n")

for i, step in enumerate(env.steps):
    s = step[0]
    obs = s.observation
    if obs.get("day") is None:
        continue
    # Once per day, at the top of the day.
    if obs.get("hour") != 0:
        continue

    me = obs["farms"][obs["player"]]
    priv = obs.get("private", {}) or {}
    tiles = me["tiles"]

    plants = weeds = empty = locked = 0
    for row in tiles:
        for t in row:
            if t is None:
                empty += 1
            elif t == "LOCKED":
                locked += 1
            elif isinstance(t, dict):
                k = t.get("kind")
                if k == "PLANT":
                    plants += 1
                elif k == "WEED":
                    weeds += 1

    shed = {k: v for k, v in (priv.get("shed") or {}).items() if v}
    seeds = {k: v for k, v in (priv.get("seeds") or {}).items() if v}
    invs = priv.get("inventories") or []
    carried = sum(sum(d.values()) for d in invs if isinstance(d, dict))

    print(
        f"day {obs['day']:>2} | ${me['money']:>6} | farmer {me['farmer']} "
        f"| plants {plants:>2} weeds {weeds:>2} empty {empty:>2} "
        f"| seeds {seeds} shed {shed} carried {carried}"
    )

final = env.steps[-1]
print(f"\nfinal: me={final[0].reward} opponent={final[1].reward} status={final[0].status}")
