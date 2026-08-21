"""Submit `main.py` to the competition, with the checks a wasted slot deserves.

This repo's rule used to be that nothing automated ever submits. That was
relaxed deliberately by the owner; the checks below are what replaces the
human in the loop, and they exist because the cost of a bad submission is
real: the daily allowance is five, a submission cannot be withdrawn, and five
instances split the episode pool, so a crashing agent burns a slot *and*
dilutes the ratings of the good ones.

Refuses to submit unless all of:

  1. the file parses and exposes `agent(obs)`
  2. it imports nothing outside the standard library -- a submitted agent runs
     without this repo, so `import main` or a helper module would fail there
     and pass here
  3. it plays a full 720-turn game without crashing, and banks something
     plausible -- the smoke test catches the whole class of bug that only
     shows up under a real environment
  4. per-turn p99 is well inside `actTimeout` (1s)
  5. the daily allowance is not already spent

    py -3.12 submit.py -m "message"      # run the checks and submit
    py -3.12 submit.py --dry-run         # run the checks only
"""
import argparse
import ast
import datetime
import os
import subprocess
import sys
import time

COMPETITION = "kaggriculture"
DAILY_LIMIT = 5
STDLIB_OK = {"os", "sys", "math", "random", "collections", "itertools",
             "functools", "heapq", "json", "time", "copy", "bisect"}


def fail(msg):
    print("REFUSING TO SUBMIT: %s" % msg)
    sys.exit(1)


def check_source(path):
    if not os.path.exists(path):
        fail("%s does not exist" % path)
    src = open(path, encoding="utf-8").read()
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        fail("%s does not parse: %s" % (path, exc))
    names = {n.name for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef)}
    if "agent" not in names:
        fail("%s defines no agent() function" % path)
    for node in ast.walk(tree):
        mods = []
        if isinstance(node, ast.Import):
            mods = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods = [node.module.split(".")[0]]
        for m in mods:
            if m not in STDLIB_OK:
                fail("%s imports %r, which will not exist on Kaggle" % (path, m))
    print("  source      ok (agent() present, stdlib-only imports)")
    return src


def smoke_test(path, seed=1000):
    """Play one real game. A submitted agent that crashes scores nothing."""
    from kaggle_environments import make
    lat = []
    import importlib.util as iu
    spec = iu.spec_from_file_location("_cand", path)
    mod = iu.module_from_spec(spec)
    spec.loader.exec_module(mod)

    def timed(obs):
        t0 = time.perf_counter()
        out = mod.agent(obs)
        lat.append((time.perf_counter() - t0) * 1000.0)
        return out

    env = make(COMPETITION, configuration={"seed": seed}, debug=True)
    env.run([timed, "starter"])
    final = env.steps[-1]
    if final[0].status != "DONE":
        fail("smoke test did not finish: status %s" % final[0].status)
    bank = final[0].reward or 0
    if bank <= 0:
        fail("smoke test banked %s -- the agent is broken" % bank)
    lat.sort()
    p99 = lat[int(len(lat) * 0.99)]
    if p99 > 250:
        fail("p99 %.0fms is too close to the 1000ms actTimeout" % p99)
    print("  smoke test  ok (bank $%s, %d turns, p99 %.2fms)"
          % (format(int(bank), ","), len(lat), p99))
    return bank


def submissions_today():
    out = subprocess.run(
        [sys.executable, "-m", "kaggle", "competitions", "submissions",
         COMPETITION, "-v"],
        capture_output=True, text=True, timeout=600).stdout
    # Kaggle's allowance resets on the **UTC** day, not the local one. Counting
    # by local date reported "0 left" against a real 4 on the first run here,
    # because Kaggle had already rolled over to the 21st.
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    n = 0
    for line in out.splitlines()[1:]:
        parts = line.split(",")
        if len(parts) > 2 and parts[2].strip().startswith(today):
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-m", "--message", default=None)
    ap.add_argument("--file", default="main.py")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--seed", type=int, default=1000)
    args = ap.parse_args()

    print("pre-flight for %s" % args.file)
    check_source(args.file)
    smoke_test(args.file, args.seed)

    used = submissions_today()
    left = DAILY_LIMIT - used
    print("  allowance   %d of %d used today, %d left" % (used, DAILY_LIMIT, left))
    if left <= 0:
        fail("the daily allowance is spent; a submission now would be rejected")

    if args.dry_run:
        print("dry run: all checks passed, nothing submitted")
        return
    if not args.message:
        fail("-m/--message is required; the description is how the ladder "
             "result is traced back to a build")

    print("submitting...")
    out = subprocess.run(
        [sys.executable, "-m", "kaggle", "competitions", "submit",
         "-c", COMPETITION, "-f", args.file, "-m", args.message],
        capture_output=True, text=True, timeout=900)
    print((out.stdout + out.stderr).strip()[-500:])
    if out.returncode != 0:
        # A bare 403 here has twice been transient -- it records no submission
        # and costs nothing against the allowance. See README.
        fail("submit failed; if this was a bare 403, retry before concluding")
    print("submitted. track it with:")
    print("  py -3.12 -m kaggle competitions submissions %s" % COMPETITION)


if __name__ == "__main__":
    main()
