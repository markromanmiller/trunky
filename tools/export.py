#!/usr/bin/env python3
"""Generate exported statement files from statement sets (Export items).

What gets exported is itself described by statements in the registry set:

    {exp} aComponent       {Export}
    {exp} theName          "motion-and-meaning site"
    {exp} anIncludedSet    {some public set}          (one or more)
    {exp} thePublishedPath "exports/motion-and-meaning-statements.csv"   (relative to ROOT)

The output holds every statement of the included sets, plus the theName/theIntention
statements (from sets readable by everyone) that define the attributes, components and
other items those statements use, so the file is readable on its own. Columns match the
trunky-ismar site: handle, attribute, attribute_name, entity, value, value_type.
Only sets readable by everyone may be included; anything else stops the export.

    python3 tools/export.py            # all exports
    python3 tools/export.py --dry-run  # report only
"""
import argparse, csv, re, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HDR = ["handle", "attribute", "entity", "value", "value_type"]
OUT_HDR = ["handle", "attribute", "attribute_name", "entity", "value", "value_type"]
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
NAME, INTENT = "acf5cebb-8d80-45ad-9a1f-a3dd48682ef6", "9ca34038-1a65-4ede-88c5-1492ab4bc249"
COMP = "90c2b9bb-ff6b-4f84-a29b-7b9e8dcfe04a"
READER, EVERYONE = "8faeaac3-1745-4d74-9d76-d4aa2550e8a9", "7f5cce91-c4cf-464a-8005-45ce5d5ee609"
EXPORT = "4d15b46f-492f-4568-95e6-dfcc778eb980"
INCLUDED_SET = "e270e670-73cb-4c76-b17b-2b82bf7ef7b1"
PUBLISHED_PATH = "add5cead-e7fc-4298-b7a3-e799b7380d34"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    by_set, set_of, rows = {}, {}, {}
    for p in (ROOT / "sets").glob("*.csv"):
        with open(p, newline="", encoding="utf-8") as f:
            by_set[p.stem] = [r for r in csv.reader(f)][1:]
        for r in by_set[p.stem]:
            set_of[r[0]], rows[r[0]] = p.stem, r
    names = {r[2]: r[3] for r in rows.values() if r[1] == NAME}
    public = {r[2] for r in rows.values() if r[1] == READER and r[3] == EVERYONE}
    definitions = defaultdict(list)  # item -> its theName/theIntention rows in public sets
    for r in rows.values():
        if r[1] in (NAME, INTENT) and set_of[r[0]] in public:
            definitions[r[2]].append(r)

    pubs = [r[2] for r in rows.values() if r[1] == COMP and r[3] == EXPORT]
    if not pubs:
        sys.exit("no Export declared")
    for pub in pubs:
        included = [r[3] for r in rows.values() if r[2] == pub and r[1] == INCLUDED_SET]
        paths = [r[3] for r in rows.values() if r[2] == pub and r[1] == PUBLISHED_PATH]
        bad = [names.get(s, s) for s in included if s not in public]
        if bad or len(paths) != 1:
            sys.exit(f"{names.get(pub, pub)}: non-public sets {bad} or {len(paths)} paths")
        out = [r for s in included for r in by_set.get(s, [])]
        have = {r[0] for r in out}
        todo = [u for r in out for u in [r[1]] + ([r[3]] if UUID.match(r[3]) else [])]
        seen = set()
        while todo:  # definitions of everything used, and of everything the definitions use
            u = todo.pop()
            if u in seen:
                continue
            seen.add(u)
            for d in definitions.get(u, []):
                if d[0] not in have:
                    out.append(d); have.add(d[0]); todo.append(d[1])
        path = ROOT / paths[0]
        print(f"{names.get(pub, pub)}: {len(out)} statements from "
              f"{', '.join(names.get(s, s) for s in included)} (+definitions) -> {path}")
        if args.dry_run:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(OUT_HDR)
            for r in out:
                w.writerow([r[0], r[1], names.get(r[1], ""), r[2], r[3], r[4]])


if __name__ == "__main__":
    main()
