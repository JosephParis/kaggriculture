"""Pull many leader replays without ever holding them on disk.

`fetch_leaders.py` keeps the raw JSON, which is fine for a hundred replays and
impossible for a thousand: they are ~30 MB each, so the 428 used for the second
cloning run would have been 13 GB. This downloads an episode, reduces it to its
board/target arrays, writes a ~75 KB shard, and deletes the JSON. Peak disk is
`--workers` replays in flight.

Shards already present are skipped, so an interrupted pull resumes and any
replays left lying about from `fetch_leaders.py` are reduced in place.

    py -3.12 stream_pull.py --shards data/shards --per-team 25
    py -3.12 build_leader_pool.py --shards data/shards --out pool.npz
"""
import argparse
import glob
import os
import subprocess

import numpy as np

import fetch_leaders as FL
from build_leader_pool import extract

SCRATCH = os.path.join("data", "_replay_scratch")


def shard_path(shards, ep):
    return os.path.join(shards, "ep-%d.npz" % ep)


def one(job):
    """Download, reduce, drop. Returns (episode, n_boards); 0 on failure."""
    ep, shards, scratch = job
    out = shard_path(shards, ep)
    if os.path.exists(out):
        return (ep, -1)
    raw = os.path.join(scratch, "episode-%d-replay.json" % ep)
    if not (os.path.exists(raw) and os.path.getsize(raw) > 1_000_000):
        subprocess.run(FL.KAGGLE + ["competitions", "replay", str(ep),
                                    "-p", scratch],
                       capture_output=True, text=True, timeout=900)
    if not (os.path.exists(raw) and os.path.getsize(raw) > 1_000_000):
        return (ep, 0)
    try:
        got = extract(raw)
    except Exception:                                  # noqa: BLE001
        got = None
    finally:
        # Reclaim the 30 MB whether or not the parse worked, or the point of
        # streaming is lost.
        try:
            os.remove(raw)
        except OSError:
            pass
    if got is None:
        return (ep, 0)
    b, g, t = got
    np.savez_compressed(out, b=b, g=g, t=t)
    return (ep, len(b))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shards", default=os.path.join("data", "shards"))
    ap.add_argument("--scratch", default=SCRATCH)
    ap.add_argument("--teams", type=int, default=20)
    ap.add_argument("--per-team", type=int, default=25)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    os.makedirs(args.shards, exist_ok=True)
    os.makedirs(args.scratch, exist_ok=True)

    picked = FL.discover(args.teams, args.per_team)
    eps = list(dict.fromkeys(e for _, _, e in picked))
    for p in glob.glob(os.path.join(args.scratch, "episode-*.json")):
        try:
            eid = int(os.path.basename(p).split("-")[1])
        except (IndexError, ValueError):
            continue
        if eid not in eps:
            eps.append(eid)

    todo = [e for e in eps if not os.path.exists(shard_path(args.shards, e))]
    print("\n%d episodes, %d already sharded, %d to do\n"
          % (len(eps), len(eps) - len(todo), len(todo)), flush=True)

    # Imported lazily: on Windows the workers re-import this module, and the
    # pool must be created after the argument parsing above.
    from concurrent.futures import ProcessPoolExecutor
    jobs = [(e, args.shards, args.scratch) for e in todo]
    done = boards = misses = 0
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for ep, n in pool.map(one, jobs):
            done += 1
            if n > 0:
                boards += n
            elif n == 0:
                misses += 1
            if done % 20 == 0:
                print("  %d/%d  %d new boards%s"
                      % (done, len(todo), boards,
                         "  %d missed" % misses if misses else ""),
                      flush=True)
    have = glob.glob(os.path.join(args.shards, "ep-*.npz"))
    print("\nshards on disk: %d  (%d missed)" % (len(have), misses), flush=True)


if __name__ == "__main__":
    main()
