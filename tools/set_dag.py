#!/usr/bin/env python3
"""Draw the statement sets as a dependency graph: an arrow from set A to set B means A uses an item that B
defines, so the sets reachable from A hold everything needed to define and interpret A.

An item is defined where its theName is (several sets if more than one names it); an item without a
name is defined where its aComponent statement is; a statement handle is defined by the set holding the
statement. Every UUID a set uses as an attribute, an entity or a uuid value counts, except that a set
needs nothing from elsewhere for an item it defines itself, an item defined in several sets counts only
its most widely readable definition, and provenance links (theProvenance) are left out: provenance says
where a statement came from, not what it means. Provenance links into sets readable by fewer groups are
listed separately. The drawing shows the
transitive reduction (an arrow implied by a longer path is left out), so reachability is unchanged.
Colours give who can read a set. A red arrow points from a set to one that fewer groups can read: some
readers of the first set cannot read the definitions it relies on. Each box also gives the number of
UUIDs the set uses that are defined nowhere.

    python3 tools/set_dag.py            # writes diagrams/sets-dag.{dot,svg,png}
"""
import csv, subprocess, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "diagrams"
NAME, COMP = "acf5cebb-8d80-45ad-9a1f-a3dd48682ef6", "90c2b9bb-ff6b-4f84-a29b-7b9e8dcfe04a"
PROV = "d9496c5d-6e55-43ca-84bf-72d565c33419"
READER = "8faeaac3-1745-4d74-9d76-d4aa2550e8a9"
EVERYONE, OWNER = "7f5cce91-c4cf-464a-8005-45ce5d5ee609", "a8845234-b0f6-49ea-87c1-d97404d0a125"
COLOURS = {"everyone": "#cfe8cf", "group": "#fde7b0", "owner": "#e3e3ef"}


def main():
    rows = {}
    for p in sorted((ROOT / "sets").glob("*.csv")):
        with open(p, newline="", encoding="utf-8") as f:
            rows[p.stem] = list(csv.reader(f))[1:]
    named, comped, handle_set, setname = defaultdict(set), defaultdict(set), {}, {}
    readers = defaultdict(set)
    for s, rs in rows.items():
        for h, a, e, v, vt in (r[:5] for r in rs):
            handle_set[h] = s
            if a == NAME:
                named[e].add(s)
                if e in rows:
                    setname[e] = v
            elif a == COMP:
                comped[e].add(s)
            elif a == READER:
                readers[e].add(v)
    group_names = {e: v for s in rows.values() for _, a, e, v, _ in (r[:5] for r in s) if a == NAME}

    def homes(x):
        return named.get(x) or comped.get(x) or ({handle_set[x]} if x in handle_set else set())

    def width(s):
        return 2 if EVERYONE in readers[s] else (1 if readers[s] - {OWNER} else 0)

    edges, undefined, prov_into, dupes = defaultdict(set), defaultdict(set), defaultdict(set), {}
    for s, rs in rows.items():
        for h, a, e, v, vt in (r[:5] for r in rs):
            if a == PROV:
                prov_into[s] |= homes(v) - {s}
                continue
            for x in (a, e, v) if vt == "uuid" else (a, e):
                hs = homes(x)
                if not hs:
                    undefined[s].add(x)
                elif s not in hs:
                    if len(hs) > 1:
                        dupes[x] = hs
                    edges[s].add(max(sorted(hs), key=width))

    def reach(start):
        seen, todo = set(), [start]
        while todo:
            for n in edges[todo.pop()]:
                if n not in seen:
                    seen.add(n)
                    todo.append(n)
        return seen
    reachable = {s: reach(s) for s in rows}
    cyclic = sorted(setname.get(s, s) for s in rows if s in reachable[s])
    # an arrow s -> t is implied when another arrow s -> m leads on to t and m is not on a cycle with t;
    # arrows within a cycle are all kept, so cycles stay visible
    reduced = {s: {t for t in edges[s]
                   if not any(t in reachable[m] and m not in reachable[t] for m in edges[s] - {t, s})}
               for s in rows}

    def kind(s):
        return "everyone" if EVERYONE in readers[s] else ("group" if readers[s] - {OWNER} else "owner")

    def reach_of(s):
        return {"everyone"} if kind(s) == "everyone" else readers[s]

    lines = ["digraph sets {", '  rankdir=TB; nodesep=0.25; ranksep=0.6; newrank=true;',
             '  node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=11];',
             '  edge [color="#666666", arrowsize=0.7];']
    for s in rows:
        groups = ", ".join(sorted(group_names.get(g, g[:8]) for g in readers[s])) or "no readers"
        extra = f"\\n{len(undefined[s])} undefined" if undefined[s] else ""
        lines.append(f'  "{s}" [label="{setname.get(s, s[:8])}\\n{len(rows[s])} statements; {groups}{extra}", '
                     f'fillcolor="{COLOURS[kind(s)]}"];')
    for s in rows:
        for t in sorted(reduced[s]):
            narrower = (kind(s) == "everyone" and kind(t) != "everyone") or \
                       (kind(s) == "group" and kind(t) == "owner") or \
                       (kind(s) == kind(t) == "group" and not readers[s] <= readers[t])
            cyc = s in reachable[t]
            style = ' [color="#c0392b", penwidth=1.6]' if narrower else (' [color="#8e44ad", style=dashed]' if cyc else "")
            lines.append(f'  "{s}" -> "{t}"' + style + ";")
    lines += ['  subgraph cluster_key { label="Key"; fontname="Helvetica"; fontsize=10; style=dashed;',
              f'    k1 [label="readable by everyone", fillcolor="{COLOURS["everyone"]}"];',
              f'    k2 [label="readable by a group", fillcolor="{COLOURS["group"]}"];',
              f'    k3 [label="owner only", fillcolor="{COLOURS["owner"]}"];',
              '    k4 [label="A -> B: A uses items B defines\\nred: B is readable by fewer groups\\ndashed purple: part of a cycle", shape=plaintext, style=""];',
              "  }", "}"]
    OUT.mkdir(exist_ok=True)
    (OUT / "sets-dag.dot").write_text("\n".join(lines) + "\n")
    for fmt in ("svg", "png"):
        subprocess.run(["dot", f"-T{fmt}", "-Gdpi=160" if fmt == "png" else "-Gdpi=72",
                        str(OUT / "sets-dag.dot"), "-o", str(OUT / f"sets-dag.{fmt}")], check=True)
    print(f"wrote {OUT}/sets-dag.{{dot,svg,png}}")
    if cyclic:
        print("sets on a cycle (not a DAG):", ", ".join(cyclic))
    for x, hs in sorted(dupes.items(), key=lambda kv: group_names.get(kv[0], "")):
        print(f"defined in several sets: {group_names.get(x, x[:8])} ({', '.join(setname.get(h, h[:8]) for h in sorted(hs))})")
    for s in rows:
        narrow = [setname.get(t, t[:8]) for t in prov_into[s] if width(t) < width(s)]
        if narrow:
            print(f"provenance of {setname.get(s, s[:8])} statements is in narrower sets: {', '.join(sorted(narrow))}")
    for s in rows:
        red = [setname.get(t, t[:8]) for t in reduced[s]
               if (kind(s) == "everyone" and kind(t) != "everyone") or (kind(s) == "group" and kind(t) == "owner")]
        if red:
            print(f"{setname.get(s, s[:8])} relies on narrower sets: {', '.join(red)}")


if __name__ == "__main__":
    sys.exit(main())
