#!/usr/bin/env python3
"""Sanity checks over the v0.7 statement sets. Exit status 1 if any ERROR.

  1  Definitions are at least as visible as their uses: every attribute and every
     uuid value a set uses must be defined (have a theName) in a set whose readers
     include all of this set's readers. Referenced statement handles likewise.
  3  Statements about statements are no more visible than the statement they describe.
  5  Registry completeness: every file is a registered StatementSet, every registered
     set has a file, every set has at least one reader and one editor group.
  6  Every uuid reference resolves to an entity or a statement handle somewhere.
     (Plus: no handle appears twice, every row is well-formed.)
  7  Every row of each published file (trunky.conf `published = path`) is in a set
     readable by everyone, with identical content.
  7b Sets readable by anyone besides the owner should not link to attic URLs, which
     only Mark's Tailscale network can open (warning; promote the file to a public host).
  9  Required slots are satisfied; each item has one theName; provenance coverage.
     These are warnings.
  10 Every System has exactly one kind of input: theQuery (it acts on Trunky rows) or
     theSource (it imports from outside Trunky).

Visibility is compared through groups: a set's reach is the set of groups that may
read it, with `everyone` covering every other group.

    python3 tools/check.py [--examples N]
"""
import argparse, csv, re, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HDR = ["handle", "attribute", "entity", "value", "value_type"]
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
NAME = "acf5cebb-8d80-45ad-9a1f-a3dd48682ef6"
INTENT = "9ca34038-1a65-4ede-88c5-1492ab4bc249"
COMP = "90c2b9bb-ff6b-4f84-a29b-7b9e8dcfe04a"
REQUIRED = "24762266-9337-4930-b88c-55b6af4e7642"
PROV = "d9496c5d-6e55-43ca-84bf-72d565c33419"
STATEMENT_SET = "a99e42d0-4408-4cae-9970-bf02dcb96848"
READER, EDITOR = "8faeaac3-1745-4d74-9d76-d4aa2550e8a9", "f587ffd4-ac5c-41a9-941f-821b05d62e1c"
EVERYONE = "7f5cce91-c4cf-464a-8005-45ce5d5ee609"
OWNER = "a8845234-b0f6-49ea-87c1-d97404d0a125"
SYSTEM = "94929d3c-fb0d-4a0f-bd83-c656a3fc207b"
QUERY = "d5df39fb-8fed-4a84-8af2-889395ffe9f7"
SOURCE = "467b485a-4dc2-4f0a-a090-e78b83d84231"
PRIVATE_FILE_HOSTS = ("attic.markromanmiller.com",)


class Report:
    def __init__(self, n):
        self.n, self.items = n, defaultdict(list)

    def add(self, level, check, msg):
        self.items[(level, check)].append(msg)

    def show(self):
        for (level, check), msgs in sorted(self.items.items(), key=lambda kv: (kv[0][0] != "ERROR", kv[0][1])):
            print(f"{level:5s} [{check}] {len(msgs)}")
            for m in msgs[: self.n]:
                print(f"        {m}")
        return any(level == "ERROR" for level, _ in self.items)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--examples", type=int, default=5)
    args = ap.parse_args()
    rep = Report(args.examples)

    conf = defaultdict(list)
    for line in (ROOT / "trunky.conf").read_text().splitlines():
        if " = " in line:
            k, v = line.split(" = ", 1)
            conf[k.strip()].append(v.strip())

    # ---- load
    files = {p.stem: p for p in (ROOT / "sets").glob("*.csv")}
    set_of, rows = {}, {}
    by_set = defaultdict(list)
    for sid, p in files.items():
        with open(p, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            if next(reader, None) != HDR:
                rep.add("ERROR", "6 format", f"{sid}: header is not {','.join(HDR)}")
            for i, r in enumerate(reader, start=2):
                if len(r) != 5 or not UUID.match(r[0]) or not UUID.match(r[1]) or not UUID.match(r[2]):
                    rep.add("ERROR", "6 format", f"{sid}:{i}: malformed row {r[:3]}")
                    continue
                if r[0] in set_of:
                    rep.add("ERROR", "6 duplicate handle", f"{r[0]} in {set_of[r[0]]} and {sid}")
                    continue
                set_of[r[0]] = sid
                rows[r[0]] = r
                by_set[sid].append(r)

    names = defaultdict(set)      # item -> {names}
    defined_in = defaultdict(set)  # item -> {sets with its theName}
    entities = set()
    for h, r in rows.items():
        entities.add(r[2])
        if r[1] == NAME:
            names[r[2]].add(r[3])
            defined_in[r[2]].add(set_of[h])

    def sh(u):
        n = sorted(names.get(u, ()))
        return "{%s:%s}" % (u[:4], n[0]) if n else "{%s}" % u[:4]

    def setname(sid):
        return sorted(names.get(sid, {sid[:8]}))[0]

    # ---- 5 registry + permissions
    registered = {r[2] for r in rows.values() if r[1] == COMP and r[3] == STATEMENT_SET}
    readers, editors = defaultdict(set), defaultdict(set)
    for r in rows.values():
        if r[1] == READER:
            readers[r[2]].add(r[3])
        elif r[1] == EDITOR:
            editors[r[2]].add(r[3])
    for sid in files:
        if sid not in registered:
            rep.add("ERROR", "5 registry", f"file sets/{sid}.csv is not a registered StatementSet")
    for sid in registered - set(files):
        rep.add("ERROR", "5 registry", f"registered set {setname(sid)} ({sid[:8]}) has no file")
    for sid in registered & set(files):
        if not readers[sid]:
            rep.add("ERROR", "5 registry", f"{setname(sid)} has no aReaderGroup")
        if not editors[sid]:
            rep.add("ERROR", "5 registry", f"{setname(sid)} has no anEditorGroup")

    def covers(t, s):
        """Can everyone who reads s also read t?"""
        rt, rs = readers[t], readers[s]
        return EVERYONE in rt or rs <= rt

    # ---- 6 resolution, 1 definition visibility, 3 meta-statement visibility
    for h, r in rows.items():
        sid = set_of[h]
        refs = [("attribute", r[1])]
        if r[4] == "uuid" or UUID.match(r[3]):
            refs.append(("value", r[3]))
        for role, u in refs:
            if u in rows:  # a statement handle
                if not covers(set_of[u], sid):
                    rep.add("ERROR", "1 visibility",
                            f"{setname(sid)}: {sh(h)} {role} is statement {sh(u)} in less visible {setname(set_of[u])}")
                continue
            if u not in entities:
                rep.add("ERROR", "6 unresolved", f"{setname(sid)}: {sh(h)} {role} {u[:8]} is defined nowhere")
                continue
            if not defined_in[u]:
                if role == "attribute":
                    rep.add("WARN", "1 unnamed attribute", f"{setname(sid)}: attribute {sh(u)} has no theName anywhere")
                continue
            if not any(covers(t, sid) for t in defined_in[u]):
                where = ", ".join(sorted(setname(t) for t in defined_in[u]))
                rep.add("ERROR", "1 visibility",
                        f"{setname(sid)}: {role} {sh(u)} is only named in less visible set(s): {where}")
        if r[2] in rows:
            target = set_of[r[2]]
            # the meta-statement's readers must all be able to read the target
            if not covers(target, sid):
                rep.add("ERROR", "3 meta visibility",
                        f"{setname(sid)}: {sh(h)} {sh(r[1])} describes {sh(r[2])} in less visible {setname(target)}")

    # ---- 7 published files
    public = {sid for sid in files if EVERYONE in readers[sid]}
    for path in conf.get("published", []):
        p = Path(path)
        if not p.exists():
            rep.add("ERROR", "7 published", f"{path} does not exist")
            continue
        with open(p, newline="", encoding="utf-8-sig") as f:
            for i, d in enumerate(csv.DictReader(f), start=2):
                h = d.get("handle", "")
                if h not in rows:
                    rep.add("ERROR", "7 published", f"{p.name}:{i}: {sh(h)} is in no statement set")
                elif set_of[h] not in public:
                    rep.add("ERROR", "7 published", f"{p.name}:{i}: {sh(h)} is in non-public {setname(set_of[h])}")
                elif [d.get(k, "") for k in HDR[1:4]] != rows[h][1:4]:
                    rep.add("ERROR", "7 published", f"{p.name}:{i}: {sh(h)} differs from its set copy")

    # ---- 7b private file links in shared sets
    for h, r in rows.items():
        sid = set_of[h]
        if (readers[sid] - {OWNER} and r[4] == "str" and r[1] not in (NAME, INTENT)
                and any(host in r[3] for host in PRIVATE_FILE_HOSTS)):
            rep.add("WARN", "7b private file link", f"{setname(sid)}: {sh(h)} {sh(r[1])} of {sh(r[2])} links to attic")

    # ---- 9 quality warnings
    comps, has_attr, req = defaultdict(set), defaultdict(set), defaultdict(set)
    for r in rows.values():
        has_attr[r[2]].add(r[1])
        if r[1] == COMP:
            comps[r[2]].add(r[3])
        elif r[1] == REQUIRED:
            req[r[2]].add(r[3])
    for e, cs in comps.items():
        for c in cs:
            for slot in req.get(c, ()):
                if slot not in has_attr[e]:
                    rep.add("WARN", "9 required slot", f"{sh(e)} ({sh(c)}) lacks {sh(slot)}")
    for u, ns in names.items():
        if len(ns) > 1:
            rep.add("WARN", "9 several names", f"{u[:8]}: {sorted(ns)}")
    with_prov = {r[2] for r in rows.values() if r[1] == PROV}
    missing = Counter(set_of[h] for h, r in rows.items() if h not in with_prov and r[1] != PROV)
    for sid, n in missing.most_common():
        rep.add("WARN", "9 no provenance", f"{setname(sid)}: {n} of {len(by_set[sid])} statements")

    # ---- 10 System input
    for e, cs in comps.items():
        if SYSTEM in cs:
            q, src = QUERY in has_attr[e], SOURCE in has_attr[e]
            if q == src:
                rep.add("ERROR", "10 system input",
                        f"System {sh(e)} has {'both theQuery and theSource' if q else 'neither theQuery nor theSource'}")

    print(f"{len(rows)} statements in {len(files)} sets\n")
    sys.exit(1 if rep.show() else 0)


if __name__ == "__main__":
    main()
