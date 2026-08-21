"""Train on the *leaders'* replays, on Kaggle's hardware instead of ours.

Paste this into a Kaggle Notebook. It is written to run there, not here, for
two reasons that are both about where the data and the compute already are:

  * **The replays we want are behind a 23 GB table.** Meta Kaggle publishes
    `EpisodeAgents.csv` (23.1 GB) and `Episodes.csv` (6.8 GB), which together
    map every simulation episode to its agents and their ratings. That is the
    only way to find episode ids belonging to a 3,100-rated player -- episode
    ids are global across all Kaggle simulations, so sampling ids blindly
    pulls Card Battle and Halite about fifteen times in sixteen. Downloading
    30 GB here is hours; on a Kaggle Notebook the dataset attaches with no
    download at all.
  * **This machine has no CUDA.** It is ARM64 with 12 CPU cores, so JAX runs
    on CPU and a training pass that takes minutes on a T4 takes hours here.
    Kaggle Notebooks give a T4 (often two) for 30 hours a week, free.

Why cloning the leaders is worth doing at all: the strong farms turn out to be
**deterministic**. Ryan Hancock plays two games with every crop identical to
the tile and banks $24k and $113k on the draw. A deterministic policy is the
easy case for imitation -- there is a single right answer per state, not a
distribution -- and it is why the local DAgger run reached parity with its
expert. The ceiling is the demonstrator, so demonstrating from a 3,100-rated
player rather than our own 714-rated heuristic is the whole point.

SETUP
  1. New Kaggle Notebook, GPU T4 x2, internet ON.
  2. Add data: the "Meta Kaggle" dataset (kaggle/meta-kaggle).
  3. Add data: this repo uploaded as a private dataset, so `nn_features.py`
     and `train_target.py` are importable. Adjust REPO below to its path.
  4. Add your Kaggle API token as a notebook Secret if the replay download
     needs auth; episodes for a competition you have entered are readable
     with the notebook's own credentials.
  5. Run. It writes `weights/leader.npz`, which `main.py` loads through
     `KAG_WEIGHTS` exactly as the local DAgger weights do.
"""
import collections
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd

META = "/kaggle/input/meta-kaggle"
REPO = "/kaggle/input/kaggriculture-repo"     # where you uploaded the repo
OUT = "/kaggle/working"
REPLAYS = os.path.join(OUT, "replays")

# Episode ids we already know belong to Kaggriculture. Used to identify the
# competition without hardcoding an id that might change.
KNOWN_EPISODES = [94924717, 95157730, 95212297, 95237546, 95652555]

TOP_N_AGENTS = 40        # how many distinct high-rated agents to pull from
EPISODES_PER_AGENT = 6   # replays per agent; each is ~30 MB


# --------------------------------------------------------------- discovery
def find_competition_id():
    """Read the competition id off episodes we already know."""
    want = set(KNOWN_EPISODES)
    for chunk in pd.read_csv(os.path.join(META, "Episodes.csv"),
                             usecols=["Id", "CompetitionId"],
                             chunksize=2_000_000):
        hit = chunk[chunk["Id"].isin(want)]
        if len(hit):
            comp = int(hit["CompetitionId"].mode().iloc[0])
            print("competition id =", comp)
            return comp
    raise SystemExit("none of the known episodes were found in Episodes.csv")


def top_agent_episodes(comp_id):
    """Episode ids belonging to the highest-rated agents in this competition.

    `EpisodeAgents.csv` carries one row per agent per episode with the rating
    it held at the time, so the leaders are found by rating rather than by
    guessing which submissions are theirs.
    """
    eps = []
    for chunk in pd.read_csv(os.path.join(META, "Episodes.csv"),
                             usecols=["Id", "CompetitionId"],
                             chunksize=2_000_000):
        eps.append(chunk[chunk["CompetitionId"] == comp_id]["Id"])
    ours = set(pd.concat(eps).tolist())
    print("episodes in this competition:", len(ours))

    keep = []
    cols = ["EpisodeId", "SubmissionId", "UpdatedScore", "Reward"]
    for chunk in pd.read_csv(os.path.join(META, "EpisodeAgents.csv"),
                             usecols=cols, chunksize=2_000_000):
        chunk = chunk[chunk["EpisodeId"].isin(ours)]
        if len(chunk):
            keep.append(chunk)
    agents = pd.concat(keep) if keep else pd.DataFrame(columns=cols)
    print("agent rows for this competition:", len(agents))

    # Rank submissions by the best rating they ever held.
    best = (agents.groupby("SubmissionId")["UpdatedScore"].max()
            .sort_values(ascending=False))
    print("top submissions by peak rating:")
    print(best.head(10))

    chosen = []
    for sub in best.head(TOP_N_AGENTS).index:
        rows = agents[agents["SubmissionId"] == sub]
        # Prefer episodes this agent won -- a loss teaches its mistakes too,
        # but the point here is to imitate what a 3,100 build does when it
        # works.
        rows = rows.sort_values("Reward", ascending=False)
        chosen += rows["EpisodeId"].head(EPISODES_PER_AGENT).tolist()
    chosen = list(dict.fromkeys(int(x) for x in chosen))
    print("episodes selected:", len(chosen))
    return chosen


def fetch(ep):
    path = os.path.join(REPLAYS, "episode-%d-replay.json" % ep)
    if os.path.exists(path):
        return path
    subprocess.run([sys.executable, "-m", "kaggle", "competitions", "replay",
                    str(ep), "-p", REPLAYS],
                   capture_output=True, text=True, timeout=900)
    return path if os.path.exists(path) else None


# ------------------------------------------------------------- dataset
def build_dataset(paths, F):
    """Board planes plus the cell each unit was sent to, per turn.

    Same target-cell labelling the local pipeline uses: predicting *where to
    send a unit* rather than which key to press, because an op like SOUTH
    encodes a destination the unit's own cell does not contain.
    """
    boards, gather, targets = [], [], []
    for path in paths:
        try:
            with open(path) as fh:
                d = json.load(fh)
        except Exception:                              # noqa: BLE001
            continue
        for seat in (0, 1):
            steps = d["steps"]
            rew = [s.get("reward") or 0 for s in steps[-1]]
            if rew[seat] < rew[1 - seat]:
                continue                # imitate the winner of each game only
            prev = None
            for i in range(0, len(steps) - 1, 2):
                obs = steps[i][0]["observation"]
                nxt = steps[i + 1][0]["observation"]
                if "farms" not in obs:
                    break
                farm = obs["farms"][seat]
                units = [farm.get("farmer")] + list(farm.get("hands") or [])
                nfarm = nxt["farms"][seat]
                nunits = [nfarm.get("farmer")] + list(nfarm.get("hands") or [])
                planes = F.encode(obs, seat)
                bi = len(boards)
                added = False
                for u, pos in enumerate(units):
                    if not pos or u >= len(nunits) or not nunits[u]:
                        continue
                    # A unit that moved reveals its heading; one that acted in
                    # place is labelled with its own cell.
                    nx, ny = nunits[u]
                    x, y = pos
                    tx, ty = (nx, ny) if (nx, ny) != (x, y) else (x, y)
                    gather.append((bi, int(y), int(x)))
                    targets.append(int(ty) * 10 + int(tx))
                    added = True
                if added:
                    boards.append(planes.astype(np.float16))
    return (np.asarray(boards, dtype=np.float16),
            np.asarray(gather, dtype=np.int32),
            np.asarray(targets, dtype=np.int16))


def main():
    sys.path.insert(0, REPO)
    import nn_features as F

    os.makedirs(REPLAYS, exist_ok=True)
    comp = find_competition_id()
    episodes = top_agent_episodes(comp)

    paths = []
    for n, ep in enumerate(episodes):
        p = fetch(ep)
        if p:
            paths.append(p)
        if n % 20 == 0:
            print("  fetched %d/%d" % (n, len(episodes)))
    print("replays on disk:", len(paths))

    B, G, T = build_dataset(paths, F)
    print("dataset: %d boards, %d labelled unit-targets" % (len(B), len(T)))
    cut = int(len(B) * 0.9)
    mtr, mte = G[:, 0] < cut, G[:, 0] >= cut
    data = os.path.join(OUT, "leader_pool.npz")
    np.savez_compressed(data,
                        Btr=B, Gtr=G[mtr], Ttr=T[mtr],
                        Bte=B, Gte=G[mte], Tte=T[mte])

    # train_target.py runs unchanged; JAX picks up the GPU automatically.
    subprocess.run([sys.executable, os.path.join(REPO, "train_target.py"),
                    "--data", data, "--out",
                    os.path.join(OUT, "weights", "leader.npz"),
                    "--epochs", "12"],
                   env=dict(os.environ, PYTHONPATH=REPO), check=True)
    print("done -- download weights/leader.npz and run the agent with")
    print("  KAG_LEARNED_UNITS=2 KAG_WEIGHTS=weights/leader.npz")


if __name__ == "__main__":
    main()
