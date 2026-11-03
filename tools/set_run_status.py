#!/usr/bin/env python3
"""Change a System's theRunStatus (draft / active / paused): writes the new statement and an
aReplacement of the old one, in the System's set.

    python3 tools/set_run_status.py "Fetch paper metadata" active
"""
import csv, datetime as dt, shutil, sys, uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from trunky_lock import write_lock

ROOT = Path(__file__).resolve().parent.parent
COMP = "90c2b9bb-ff6b-4f84-a29b-7b9e8dcfe04a"
NAME = "acf5cebb-8d80-45ad-9a1f-a3dd48682ef6"
NOTE = "29a25e0e-3f32-4787-965e-3ecc917d6fef"
PROV = "d9496c5d-6e55-43ca-84bf-72d565c33419"
PROVINFO = "622966de-0519-4a9b-a2d5-95a99850ba42"

RUN_STATUS = "59add860-b99c-4fbf-9688-28c1ef54c3b2"
SYSTEM = "94929d3c-fb0d-4a0f-bd83-c656a3fc207b"
REPLACEMENT = "8f9dc95b-c4d3-4500-9a6c-9ddc63cdecf9"
OPTIONS = ("draft", "active", "paused")


def main():
    name, status = sys.argv[1], sys.argv[2]
    if status not in OPTIONS:
        sys.exit(f"status must be one of {OPTIONS}")
    u = lambda: str(uuid.uuid4())
    with write_lock(who="set_run_status"):
        rows = [(p.stem, r) for p in (ROOT / "sets").glob("*.csv") for r in list(csv.reader(open(p)))[1:] if len(r) >= 5]
        systems = {r[2] for _, r in rows if r[1] == COMP and r[3] == SYSTEM}
        ids = [r[2] for _, r in rows if r[1] == NAME and r[3] == name and r[2] in systems]
        if len(ids) != 1:
            sys.exit(f"{len(ids)} Systems named {name!r}")
        replaced = {r[2] for _, r in rows if r[1] == REPLACEMENT}
        current = [(s, r) for s, r in rows if r[1] == RUN_STATUS and r[2] == ids[0] and r[0] not in replaced]
        if len(current) != 1:
            sys.exit(f"expected one current theRunStatus, found {len(current)}")
        s, old = current[0]
        if old[3] == status:
            sys.exit(f"already {status}")
        new, prov = u(), u()
        out = [[new, RUN_STATUS, ids[0], status, "str"], [u(), REPLACEMENT, old[0], new, "uuid"],
               [u(), COMP, prov, PROVINFO, "uuid"],
               [u(), NOTE, prov, f"theRunStatus {old[3]} -> {status} at Mark's request, "
                                 f"{dt.datetime.now().astimezone():%Y-%m-%d %H:%M}.", "str"]]
        out += [[u(), PROV, h, prov, "uuid"] for h in (out[0][0], out[1][0])]
        backup = ROOT / "backups" / f"run-status-{dt.datetime.now():%Y%m%d-%H%M%S}"
        backup.mkdir(parents=True)
        shutil.copy2(ROOT / "sets" / f"{s}.csv", backup / f"{s}.csv")
        with open(ROOT / "sets" / f"{s}.csv", "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(out)
    print(f"{name}: {old[3]} -> {status}")


if __name__ == "__main__":
    main()
