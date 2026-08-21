"""Does the price projection actually forecast? Measure it before trusting it.

`main._projected_price` claims to say what a product will fetch when a crop
planted today ripens. That claim is testable: record the projection made on
day d for a horizon h, then look at what the price actually was on day d+h.

An adaptive policy is only as good as its forecast, and a forecast that is
worse than "assume today's price holds" is worse than no model at all. So the
naive carry-forward is scored alongside as the baseline to beat.

    py -3.12 check_forecast.py [--games 3] [--opponent starter]
"""
import argparse
import collections

import main

HORIZONS = (4, 10, 16)
WATCH = ("MELON", "STRAWBERRY", "MILK", "WHEAT", "WOOL")


def main_cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=3)
    ap.add_argument("--opponent", default="starter")
    ap.add_argument("--seed", type=int, default=1000)
    args = ap.parse_args()

    from kaggle_environments import make

    err = collections.defaultdict(list)     # (item, h) -> [|proj - actual|]
    naive = collections.defaultdict(list)   # same, for today's price held

    for g in range(args.games):
        seen = {}       # day -> {item: actual price}
        preds = []      # (target_day, item, h, projected, today)

        def traced(obs):
            if obs["hour"] == 12:
                day = obs["day"]
                prices = dict(obs["market"]["prices"])
                seen[day] = prices
                view = main._market_view(obs, obs["player"])
                for item in WATCH:
                    for h in HORIZONS:
                        preds.append((day + h, item, h,
                                      main._projected_price(view, item, h),
                                      prices.get(item, 0)))
            return main.agent(obs)

        env = make("kaggriculture", configuration={"seed": args.seed + g},
                   debug=False)
        env.run([traced, args.opponent])

        for target, item, h, proj, today in preds:
            actual = seen.get(target, {}).get(item)
            if actual is None:
                continue
            err[(item, h)].append(abs(proj - actual))
            naive[(item, h)].append(abs(today - actual))

    print("mean absolute error of the %d-day price forecast" % 0)
    print("  %-12s %4s %10s %10s %8s" % ("item", "h", "projected", "naive",
                                         "better?"))
    wins = total = 0
    for item in WATCH:
        for h in HORIZONS:
            a, b = err.get((item, h)), naive.get((item, h))
            if not a:
                continue
            ma = sum(a) / len(a)
            mb = sum(b) / len(b)
            total += 1
            better = ma < mb
            wins += better
            print("  %-12s %4d %10.1f %10.1f %8s"
                  % (item, h, ma, mb, "yes" if better else "no"))
    print("")
    print("  projection beats carry-forward on %d of %d item/horizon pairs"
          % (wins, total))


if __name__ == "__main__":
    main_cli()
