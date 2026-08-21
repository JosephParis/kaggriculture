"""Download episode replays, record who won, and keep the losses.

Replays are ~25MB each, so wins are deleted once summarised and only the games
we lost are kept on disk for analysis.

    py -3.12 scan_episodes.py <submission_id> [--limit 20]

Prints one line per episode and writes `replays/summary_<submission>.csv`.
"""
import argparse
import json
import os
import subprocess
import sys

REPLAYS = "replays"


def episode_ids(submission, limit):
    out = subprocess.run(
        [sys.executable, "-m", "kaggle", "competitions", "episodes",
         str(submission), "-v"],
        capture_output=True, text=True, timeout=600).stdout
    ids = []
    for line in out.strip().splitlines()[1:]:
        part = line.split(",")[0].strip()
        if part.isdigit():
            ids.append(part)
    return ids[:limit]


def fetch(ep):
    path = os.path.join(REPLAYS, "episode-%s-replay.json" % ep)
    if not os.path.exists(path):
        subprocess.run(
            [sys.executable, "-m", "kaggle", "competitions", "replay", ep,
             "-p", REPLAYS],
            capture_output=True, text=True, timeout=900)
    return path if os.path.exists(path) else None


def summarise(path):
    with open(path) as f:
        d = json.load(f)
    names = [a.get("Name") for a in d.get("info", {}).get("Agents", [])]
    final = d["steps"][-1]
    rewards = [s.get("reward") or 0 for s in final]
    mine = 0 if names and names[0] == "Joseph Paris" else 1
    them = 1 - mine
    return {
        "me": rewards[mine], "them": rewards[them],
        "opponent": names[them] if len(names) > them else "?",
        "seat": mine, "won": rewards[mine] > rewards[them],
        "tie": rewards[mine] == rewards[them],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("submission")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--keep-all", action="store_true",
                    help="keep winning replays too; cloning needs them")
    args = ap.parse_args()

    if not os.path.isdir(REPLAYS):
        os.makedirs(REPLAYS)

    rows = []
    for ep in episode_ids(args.submission, args.limit):
        path = fetch(ep)
        if path is None:
            print("  %s  DOWNLOAD FAILED" % ep)
            continue
        try:
            got = summarise(path)
        except Exception as exc:                       # noqa: BLE001
            print("  %s  PARSE FAILED %s" % (ep, exc))
            continue
        verdict = "TIE " if got["tie"] else ("WIN " if got["won"] else "LOSS")
        print("  %s  %s  seat%d  %9.0f vs %9.0f  %s"
              % (ep, verdict, got["seat"], got["me"], got["them"],
                 got["opponent"]))
        rows.append((ep, verdict.strip(), got))
        # Wins are 25MB apiece and only the losses are re-read for analysis --
        # but behavioural cloning wants the *winning* seat of every episode,
        # which in a win is ours. --keep-all stops the pruning.
        if got["won"] and not args.keep_all:
            os.remove(path)

    losses = [r for r in rows if r[1] == "LOSS"]
    print("\n%d episodes: %dW %dL %dT" % (
        len(rows), sum(1 for r in rows if r[1] == "WIN"), len(losses),
        sum(1 for r in rows if r[1] == "TIE")))
    out = os.path.join(REPLAYS, "summary_%s.csv" % args.submission)
    with open(out, "w") as f:
        f.write("episode,verdict,me,them,opponent,seat\n")
        for ep, verdict, g in rows:
            f.write("%s,%s,%s,%s,%s,%s\n" % (
                ep, verdict, g["me"], g["them"], g["opponent"], g["seat"]))
    print("kept %d loss replays; summary -> %s" % (len(losses), out))


if __name__ == "__main__":
    main()
