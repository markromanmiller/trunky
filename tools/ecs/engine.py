#!/usr/bin/env python3
"""ECS engine, minimal first version (proposals/ecs-engine-design.md).

A pass: build the current view, evaluate each System, act on each result row, and repeat while a
round wrote something (at most 10 rounds). A System's input is either theQuery (SPARQL over Trunky; its
code runs once per result row) or theSource (something outside Trunky that it imports, such as a folder;
its code runs once per source per evaluation, with the row {"source": <uuid>}). A Code System needs
exactly one of the two. Code Systems run their function; Claude Systems hand each
item to a headless Claude run and write what its output check accepts (tools/ecs/claude_actor.py); Systems
with other actors are listed and skipped. New statements go to the home set of the entity they describe (the set holding
its first aComponent statement), or to the set a result names under "set" (needed for new items), each
with a provenance item naming the System. A System with theRunInterval (ISO 8601 duration, e.g. PT15M)
is evaluated at most once per interval; the last evaluation time is kept in the state file.

Errors: when a System's query or function raises, the results it already produced are still written,
the traceback goes to stderr (the journal, under systemd), and a claude-stop Paug task is filed. The
System then backs off: it is skipped for 1, 4, 16, 64, ... minutes (factor 4, capped at 1 day) after
each consecutive failure, and the count resets on its next clean run. A pass-level failure (e.g. the
view can't be built) is handled the same way under the key "engine". State: state/ecs-engine.json.
Running a single System by hand (--system) ignores its backoff.

    .venv/bin/python tools/ecs/engine.py                          # one pass over active Systems
    .venv/bin/python tools/ecs/engine.py --system "Fetch paper metadata"   # one System, any status
    .venv/bin/python tools/ecs/engine.py --system ... --dry-run   # show what it would write
"""
import argparse, csv, datetime as dt, importlib.util, json, re, sys, traceback, uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from view import ROOT, View, conf
import claude_actor
from trunky_lock import write_lock

COMP = "90c2b9bb-ff6b-4f84-a29b-7b9e8dcfe04a"
NAME = "acf5cebb-8d80-45ad-9a1f-a3dd48682ef6"
NOTE = "29a25e0e-3f32-4787-965e-3ecc917d6fef"
PROV = "d9496c5d-6e55-43ca-84bf-72d565c33419"
PROVINFO = "622966de-0519-4a9b-a2d5-95a99850ba42"
RECORDED = "a1e6a161-773d-4011-aaa6-13869931f59f"
SYSTEM = "94929d3c-fb0d-4a0f-bd83-c656a3fc207b"
ACTOR = "877c38ac-77f1-48af-af99-0bc5bba1d50c"
INSTRUCTIONS = "c0e84db4-c765-4503-b1b8-943ef1472b09"
QUERY = "d5df39fb-8fed-4a84-8af2-889395ffe9f7"
RUN_STATUS = "59add860-b99c-4fbf-9688-28c1ef54c3b2"
RUN_INTERVAL = "3c625ba6-75a3-44df-b71a-1ee482d69c5c"
OUTPUT_CHECK = "c29d587b-d804-4950-bc2e-0e939df0a15a"
ALLOWED_TOOL = "ca7d965f-3ed3-43f2-b43b-8becdb43e627"
DAILY_LIMIT = "1d3f9b22-2599-405d-8bc1-fbf542251196"
MODEL = "63a437ec-0aaa-4c3a-bc1f-cc5546d3dd94"
EFFORT = "8ae31291-ca18-4dcb-a7e2-b0035f7db0e0"
SOURCE = "467b485a-4dc2-4f0a-a090-e78b83d84231"
MAX_ROUNDS = 10
STATE = ROOT / "state" / "ecs-engine.json"
TASKS = Path(conf("tasks_dir", ROOT / "state" / "tasks"))   # where failures and approvals are filed as notes
BACKOFF_BASE_MIN, BACKOFF_FACTOR, BACKOFF_CAP_MIN = 1, 4, 24 * 60
TASK_TEMPLATE = """---
gtd: task
gtd-today: {today}
gtd-status: claude-stop
gtd-today-rank:
gtd-context:
gtd-minutes:
gtd-role:
---

"""


def load_state():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save_state(state):
    STATE.write_text(json.dumps(state, indent=2) + "\n")


def backing_off(state, key):
    until = (state.get(key) or {}).get("retry_after")
    return until and dt.datetime.fromisoformat(until) > dt.datetime.now().astimezone()


def file_task(title, status, body):
    """A Paug task note (status claude-stop or claude-go) in the tasks folder."""
    TASKS.mkdir(parents=True, exist_ok=True)
    title = re.sub(r'[\\/:*?"<>|#^\[\]]+', "-", title)
    text = TASK_TEMPLATE.format(today=dt.date.today().isoformat()).replace("gtd-status: claude-stop", f"gtd-status: {status}")
    (TASKS / f"{title}.md").write_text(text + body)


def record_failure(state, key, label, detail):
    """Count the failure, set the next retry time, log it, and file a claude-stop task."""
    now = dt.datetime.now().astimezone()
    n = (state.get(key) or {}).get("failures", 0) + 1
    wait = min(BACKOFF_BASE_MIN * BACKOFF_FACTOR ** (n - 1), BACKOFF_CAP_MIN)
    retry = now + dt.timedelta(minutes=wait)
    state[key] = {"failures": n, "retry_after": retry.isoformat(timespec="seconds"), "last_error": detail[-2000:]}
    save_state(state)
    print(f"ERROR in {label} (failure {n}; next try after {retry:%H:%M}):\n{detail}", file=sys.stderr)
    title = f"ECS engine error in {label} ({now:%Y-%m-%d %H%M}, failure {n})"
    body = (f"The ECS engine hit an error in {label}.\n\n"
            f"Consecutive failures: {n}. Skipped until {retry:%a %b %d %I:%M %p} (backoff x{BACKOFF_FACTOR}).\n"
            f"Log: journalctl --user -u trunky-ecs\n\n```\n{detail.strip()}\n```\n")
    TASKS.mkdir(parents=True, exist_ok=True)
    (TASKS / f"{title}.md").write_text(TASK_TEMPLATE.format(today=now.date().isoformat()) + body)


def record_success(state, key):
    if key in state:
        del state[key]
        save_state(state)


def parse_duration(s):
    """ISO 8601 duration (PnDTnHnMnS; weeks as PnW) as a timedelta."""
    m = re.fullmatch(r"P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", s.strip())
    if not m or not any(m.groups()):
        raise ValueError(f"bad theRunInterval {s!r}")
    w, d, h, mi, se = (int(x or 0) for x in m.groups())
    return dt.timedelta(weeks=w, days=d, hours=h, minutes=mi, seconds=se)


def not_due(state, system):
    """When an interval System is not due yet, the time it next is; otherwise None."""
    last = (state.get("last_run") or {}).get(system["id"])
    if not (system["interval"] and last):
        return None
    due = dt.datetime.fromisoformat(last) + parse_duration(system["interval"])
    return due if due > dt.datetime.now().astimezone() else None


def systems(view):
    out = []
    for e in {r[3] for r in view.current if r[2] == COMP and r[4] == SYSTEM}:
        one = lambda a: (view.values(e, a) or [None])[0]
        out.append({"id": e, "name": one(NAME) or e[:8], "actor": one(ACTOR), "instructions": one(INSTRUCTIONS),
                    "query": one(QUERY), "sources": sorted(view.values(e, SOURCE)), "status": one(RUN_STATUS),
                    "interval": one(RUN_INTERVAL), "output_check": one(OUTPUT_CHECK),
                    "tools": sorted(view.values(e, ALLOWED_TOOL)), "daily_limit": one(DAILY_LIMIT),
                    "model": one(MODEL), "effort": one(EFFORT)})
    return sorted(out, key=lambda s: s["name"])


def load_function(ref):
    path, func = ref.rsplit(":", 1)
    spec = importlib.util.spec_from_file_location(Path(path).stem, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, func)


def write(view, system, results):
    """Append each result's statements, with one provenance item per result, to the entity's home set."""
    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    by_set = {}
    for res in results:
        if not res["statements"]:
            continue
        prov = str(uuid.uuid4())
        target = res.get("set") or view.home[res["statements"][0][1]]
        rows = by_set.setdefault(target, [])
        rows += [[str(uuid.uuid4()), COMP, prov, PROVINFO, "uuid"],
                 [str(uuid.uuid4()), NOTE, prov, f"Written by System {system['name']} ({system['id']}): {res['note']}", "str"],
                 [str(uuid.uuid4()), RECORDED, prov, now, "str"]]
        for st in res["statements"]:
            a, e, v, vt = st[:4]
            h = st[4] if len(st) > 4 else str(uuid.uuid4())
            rows += [[h, a, e, v, vt], [str(uuid.uuid4()), PROV, h, prov, "uuid"]]
    for s, rows in by_set.items():
        with open(ROOT / "sets" / f"{s}.csv", "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(rows)
    return sum(len(r) for r in by_set.values())


def run_claude_system(view, system, dry_run, state, by_hand):
    """Collect finished Claude runs and write what their check accepts; when due, start runs for new items."""
    key = system["id"]
    if dry_run:
        rows = view.query(system["query"])
        print(f"  {system['name']} (actor Claude): {len(rows)} item(s); dry run starts and collects nothing")
        for row in rows:
            print(f"    {row}")
        return 0
    results, lines = claude_actor.collect(system, view, state, file_task)
    for line in lines:
        print(f"  {system['name']}: {line}")
    written = write(view, system, results)
    save_state(state)
    if backing_off(state, key) and not by_hand:
        print(f"  skip {system['name']}: backing off until {state[key]['retry_after']}")
        return written
    due = not_due(state, system)
    if due and not by_hand:
        print(f"  skip {system['name']}: next run after {due:%H:%M}")
        return written
    state.setdefault("last_run", {})[key] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        rows = view.query(system["query"])
        print(f"  {system['name']}: {len(rows)} item(s)")
        for row in rows:
            print(f"    {claude_actor.start(system, row, view, state, file_task)}: {row}")
    except Exception:
        save_state(state)
        record_failure(state, key, f"System {system['name']}", traceback.format_exc())
        return written
    save_state(state)
    record_success(state, key)
    return written


def run_system(view, system, dry_run, state, by_hand):
    key, label = system["id"], f"System {system['name']}"
    if system["actor"] == "Claude":
        return run_claude_system(view, system, dry_run, state, by_hand)
    if system["actor"] != "Code":
        print(f"  skip {system['name']}: actor {system['actor']!r} not handled yet")
        return 0
    if backing_off(state, key) and not by_hand:
        print(f"  skip {system['name']}: backing off until {state[key]['retry_after']}")
        return 0
    due = not_due(state, system)
    if due and not by_hand:
        print(f"  skip {system['name']}: next run after {due:%H:%M}")
        return 0
    if not dry_run:
        state.setdefault("last_run", {})[key] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        save_state(state)
    results, error = [], None
    try:
        if bool(system["query"]) == bool(system["sources"]):
            raise ValueError(f"System {system['name']} needs exactly one of theQuery and theSource")
        rows = view.query(system["query"]) if system["query"] else [{"source": s} for s in system["sources"]]
        print(f"  {system['name']}: {len(rows)} item(s)")
        func = load_function(system["instructions"])
        for row in rows:
            try:
                res = func(row, view)
            except Exception:
                error = f"item {row}\n{traceback.format_exc()}"
                break
            print(f"    {res['note']}; {len(res['statements'])} statement(s)")
            if dry_run:
                for st in res["statements"]:
                    print(f"      {st[0][:4]} of {st[1][:4]} is {st[2][:90]!r}")
            results.append(res)
    except Exception:
        error = traceback.format_exc()
    written = 0 if dry_run else write(view, system, results)
    if error:
        record_failure(state, key, label, error)
    elif not dry_run:
        record_success(state, key)
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", help="run only this System (name or uuid prefix), whatever its status")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    state = load_state()
    if backing_off(state, "engine") and not args.system:
        print(f"engine backing off until {state['engine']['retry_after']}")
        return
    with write_lock(who="ecs-engine"):
        try:
            for rnd in range(1, MAX_ROUNDS + 1):
                view = View()
                chosen = [s for s in systems(view) if (s["name"] == args.system or s["id"].startswith(args.system))] \
                    if args.system else [s for s in systems(view) if s["status"] == "active"]
                if args.system and not chosen:
                    sys.exit(f"no System named {args.system!r}")
                print(f"round {rnd}")
                written = sum(run_system(view, s, args.dry_run, state, bool(args.system)) for s in chosen)
                print(f"  wrote {written} row(s)")
                if not written or args.dry_run:
                    break
        except SystemExit:
            raise
        except Exception:
            record_failure(state, "engine", "the engine pass", traceback.format_exc())
            sys.exit(1)
        if not args.system:
            record_success(state, "engine")


if __name__ == "__main__":
    main()
