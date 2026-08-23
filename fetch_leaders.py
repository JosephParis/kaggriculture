"""Pull the top-rated teams' replays straight from the competition API.

`kaggle_train_notebook.py` routed this through Meta Kaggle's 23 GB
`EpisodeAgents.csv` on a Kaggle Notebook, on the premise that there is no API
from a leaderboard team to its episodes. CLI 2.2.4 has one:

    leaderboard --show  ->  team-submissions <team>  ->  episodes <submission>
                        ->  replay <episode>

So this runs here, in minutes, against no quota and no 30 GB download. Each
replay is ~30 MB; 149 of them took about fifteen minutes.

    py -3.12 fetch_leaders.py --out data/leader_replays --per-team 10

Feed the result to `build_leader_pool.py`.
"""
import argparse
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor

KAGGLE = ["py", "-3.12", "-m", "kaggle"]     # see TRIED.md: 2.2.4, not 1.7.x
COMP = "kaggriculture"


def run(args, timeout=300):
    p = subprocess.run(KAGGLE + args, capture_output=True, text=True,
                       timeout=timeout)
    return p.stdout, p.stderr, p.returncode


def jload(out):
    """Decode the JSON array out of the CLI's chatter.

    It prints a page token before the array and a "use kaggle competitions
    replay ..." hint after it, so a plain `json.loads` raises "Extra data".
    """
    i = out.find("[")
    if i < 0:
        return []
    try:
        obj, _ = json.JSONDecoder().raw_decode(out[i:])
        return obj
    except json.JSONDecodeError:
        return []


def discover(teams_wanted, per_team):
    """(team_id, rating, episode_id) for the best submission of each team."""
    out, err, _ = run(["competitions", "leaderboard", COMP, "-s",
                       "--format", "json"])
    teams = jload(out)[:teams_wanted]
    if not teams:
        raise SystemExit("no leaderboard rows: %s%s" % (out[:400], err[:400]))
    print("top %d teams, rated %s down to %s"
          % (len(teams), teams[0]["score"], teams[-1]["score"]), flush=True)

    picked = []
    for t in teams:
        out, _, _ = run(["competitions", "team-submissions",
                         str(t["teamId"]), "--format", "json"])
        subs = jload(out)
        if not subs:
            print("  team %s: no submissions" % t["teamId"], flush=True)
            continue
        best = max(subs, key=lambda s: float(s.get("publicScore") or 0))
        out, _, _ = run(["competitions", "episodes", str(best["id"]),
                         "--format", "json"])
        eps = [int(e["id"]) for e in jload(out)
               if str(e.get("state", "")).endswith("COMPLETED")]
        picked += [(int(t["teamId"]), float(best.get("publicScore") or 0), e)
                   for e in eps[:per_team]]
        print("  team %-9s rated %-7s %3d episodes, taking %d"
              % (t["teamId"], best.get("publicScore"), len(eps),
                 min(len(eps), per_team)), flush=True)
    return picked


def fetch(ep, out_dir):
    path = os.path.join(out_dir, "episode-%d-replay.json" % ep)
    if os.path.exists(path) and os.path.getsize(path) > 1_000_000:
        return path
    _, err, rc = run(["competitions", "replay", str(ep), "-p", out_dir],
                     timeout=900)
    if os.path.exists(path) and os.path.getsize(path) > 1_000_000:
        return path
    print("  MISS %d rc=%d %s" % (ep, rc, (err or "")[:160]), flush=True)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join("data", "leader_replays"))
    ap.add_argument("--teams", type=int, default=20)
    ap.add_argument("--per-team", type=int, default=10)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    picked = discover(args.teams, args.per_team)
    # The leaders largely play each other, so the same episode arrives from
    # both sides: 20 teams x 10 deduped to 149.
    eps = list(dict.fromkeys(e for _, _, e in picked))
    print("\n%d distinct episodes to fetch\n" % len(eps), flush=True)
    with open(os.path.join(args.out, "_index.json"), "w") as fh:
        json.dump({"episodes": picked}, fh)

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for _ in pool.map(lambda e: fetch(e, args.out), eps):
            done += 1
            if done % 10 == 0:
                mb = sum(os.path.getsize(os.path.join(args.out, f))
                         for f in os.listdir(args.out) if f.endswith(".json"))
                print("  %d/%d  (%.1f GB on disk)"
                      % (done, len(eps), mb / 1e9), flush=True)
    have = [f for f in os.listdir(args.out) if f.startswith("episode-")]
    print("\nreplays on disk: %d" % len(have), flush=True)


if __name__ == "__main__":
    main()
