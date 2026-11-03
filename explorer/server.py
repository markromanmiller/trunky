#!/usr/bin/env python3
"""Trunky Explorer: serves the browser page and the current statements a viewer may read.

The current view is tools/ecs/view.py's (replacements, errata, removal times and empty values applied),
reloaded whenever a set file changes, so edits show on the next refresh. A viewer reads the sets whose
aReaderGroup is everyone or a group the viewer is aMember of; nothing from other sets is sent.

Served over Tailscale only (`tailscale serve`), so every request comes from the owner. When a login front
door (Authelia) is added, viewer() should map its user header to a Person instead.

With --public the viewer is anonymous: only sets whose aReaderGroup is everyone are sent, and only the page
itself is served (no other static files). This is the instance behind trunky.dev.markromanmiller.com.

Replies (2026-10-28): POST /api/reply {question, to, text} writes "aReply of <to> is <text>", where <to> is
the Question (a questioned statement's handle) or a reply in its thread, plus "aToDo of <question> is ...",
so the reply gets acted on. Both go to the set holding the Question, with provenance naming the viewer and
the Explorer, under the Trunky write lock. Never on the --public instance. The request must carry the header
X-Trunky-Explorer and a JSON body, so another site's page cannot send one (no CORS preflight is answered).

Edits (2026-11-02): POST /api/edit {handle, text} replaces one current statement: it appends
"<attribute> of <entity> is <entry>" and "aReplacement of <handle> is <the new statement>" to the set holding
the old statement, with provenance as for replies. Refused if the viewer is not in the set's anEditorGroup, if
the statement is not current (for instance, replaced since the page loaded), or if the entry is empty or
unchanged. GET /api/synced lists {item: [attributes]} that the Paug sync tracks
(state/paug-sync-base.json), so the page can warn that an edit there does not reach the Obsidian note yet.

Adding a value (2026-11-02; any attribute in use since 2026-11-03): POST /api/add {entity, attribute, text}
writes "<attribute> of <entity> is <entry>" when the entity has no current value for the attribute and the
attribute is a slot of one of the entity's components or is used by some current statement (so a table column
can take a value in an empty cell). It goes to the set holding the aComponent statement that declares the slot,
else one of the entity's aComponent statements, else its theName, with provenance as above.

Every write answers {"ok": true, "rows": [...], "set": <set id>} (plus "id" for a new item): the rows it
appended, so the page can apply them without downloading everything again.

New items (2026-11-03): POST /api/new {component, set, name} makes a new UUID and writes "aComponent of <it> is
<component>" and "theName of <it> is <name>" to the chosen set, with provenance as above; it answers with the
new id. The component must already be some current item's aComponent value, and the viewer must be in the
set's anEditorGroup.

Adding a component (2026-11-03): POST /api/component {entity, component} writes "aComponent of <entity> is
<component>" to the set holding one of the entity's aComponent statements (else its theName), among the sets
the viewer may edit. Refused if the component is not in use, if the entity already carries it, or if no such
set exists.

Entries (edit, add and new) are text, read by entry_value(): an entry that is exactly {{<uuid>}} is stored as that
uuid (a link to an item); an entry starting with '{{ is text with the ' dropped, so '{{x}} stores {{x}}; any
other entry containing {{ ... }} as its whole value is refused as a mistyped link. Everything else is stored as
str, whatever type the old value had (no value-type checks, by design).

    .venv/bin/python explorer/server.py [port] [--public]     # default 8850, bound to 127.0.0.1
"""
import csv, datetime as dt, gzip, hashlib, json, re, sys, uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "ecs"))
from view import ROOT, current  # noqa: E402
sys.path.insert(0, str(HERE.parent / "tools"))
from trunky_lock import write_lock  # noqa: E402

NAME = "acf5cebb-8d80-45ad-9a1f-a3dd48682ef6"
READER = "8faeaac3-1745-4d74-9d76-d4aa2550e8a9"
MEMBER = "d512b1b7-079f-4447-a5a0-0a761ca3427d"
EVERYONE = "7f5cce91-c4cf-464a-8005-45ce5d5ee609"
MARK = "01567ad3-e1cd-4a9d-8332-2df55c3523f1"
COMP = "90c2b9bb-ff6b-4f84-a29b-7b9e8dcfe04a"
NOTE = "29a25e0e-3f32-4787-965e-3ecc917d6fef"
PROV = "d9496c5d-6e55-43ca-84bf-72d565c33419"
PROVINFO = "622966de-0519-4a9b-a2d5-95a99850ba42"
RECORDED = "a1e6a161-773d-4011-aaa6-13869931f59f"
QUESTION = "305ecea2-6a7e-4a84-98e9-af4ee25e6a69"
REPLY = "f7b91816-d622-4178-bf0e-10bad96d7745"
TODO = "e1f0b9ec-74cc-4fa0-b824-ab9eae0aee17"
EDITOR = "f587ffd4-ac5c-41a9-941f-821b05d62e1c"
REPLACEMENT = "8f9dc95b-c4d3-4500-9a6c-9ddc63cdecf9"
SLOTS = {"24762266-9337-4930-b88c-55b6af4e7642", "8a707bcb-7ff7-488f-b7e3-b1679f823c95",
         "e8d0e88d-a8ea-4612-8e8c-a4be732d1a93"}   # aRequiredSlot, aDesirableSlot, anOptionalSlot
MAX_REPLY = 4000
MAX_EDIT = 20000
SYNC_BASE = ROOT / "state" / "paug-sync-base.json"
ANONYMOUS = "anonymous"   # a member of no group, so it reads only the sets everyone may read
PUBLIC = "--public" in sys.argv
PUBLIC_PATHS = {"/", "/index.html"}


def viewer(headers):
    return ANONYMOUS if PUBLIC else MARK


class Store:
    def __init__(self):
        self.lock, self.stamp, self.rows = Lock(), None, []
        self.cache = {}

    def _load(self):
        paths = sorted((ROOT / "sets").glob("*.csv"))
        stamp = tuple((p.name, p.stat().st_mtime_ns, p.stat().st_size) for p in paths)
        if stamp == self.stamp:
            return
        rows = []
        for p in paths:
            with open(p, newline="", encoding="utf-8") as f:
                rows += [(p.stem, *r[:5]) for r in list(csv.reader(f))[1:] if len(r) >= 5]
        self.stamp, self.rows, self.cache = stamp, current(rows), {}

    def payload(self, person):
        """(etag, gzipped JSON) of the sets this person can read and their current statements."""
        with self.lock:
            self._load()
            if person not in self.cache:
                rows = self.rows
                groups = {EVERYONE} | {e for _, _, a, e, v, _ in rows if a == MEMBER and v == person}
                readable = sorted({e for _, _, a, e, v, _ in rows if a == READER and v in groups})
                if not any(a == READER for _, _, a, _, _, _ in rows):
                    # no permissions set (e.g. a clone of the public repository): show every set file present
                    readable = sorted({s for s, *_ in rows})
                names = {e: v for _, _, a, e, v, _ in rows if a == NAME and e in readable}
                editable = set() if PUBLIC else {e for _, _, a, e, v, _ in rows if a == EDITOR and v in groups}
                index = {s: i for i, s in enumerate(readable)}
                counts = [0] * len(readable)
                out = []
                for s, h, a, e, v, vt in rows:
                    if s in index:
                        out.append([h, a, e, v, vt, index[s]])
                        counts[index[s]] += 1
                body = json.dumps({"viewer": person,
                                   "sets": [{"id": s, "name": names.get(s, s[:8]), "statements": counts[i],
                                             "edit": s in editable}
                                            for i, s in enumerate(readable)],
                                   "rows": out}, separators=(",", ":")).encode()
                self.cache[person] = ('"' + hashlib.sha1(body).hexdigest()[:16] + '"', gzip.compress(body, 6))
            return self.cache[person]


STORE = Store()


def append(set_id, out, **extra):
    """Append rows to a set under the write lock; returns what the page needs to update without a reload."""
    with write_lock(wait=True, who="trunky-explorer"):
        with open(ROOT / "sets" / f"{set_id}.csv", "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(out)
    return {"rows": out, "set": set_id, **extra}


def write_reply(person, question, to, text):
    """Append a reply to a Question's thread; returns the appended rows, or the reason it was refused."""
    text = (text or "").strip()
    if not text or len(text) > MAX_REPLY:
        return f"a reply must be 1 to {MAX_REPLY} characters"
    with STORE.lock:
        STORE._load()
        rows = STORE.rows
    home = next((s for s, _, a, e, v, _ in rows if a == COMP and e == question and v == QUESTION), None)
    if not home:
        return "not a current Question"
    thread, frontier = {question}, [question]
    while frontier:
        nxt = [h for _, h, a, e, _, _ in rows if a == REPLY and e in frontier]
        thread.update(nxt)
        frontier = nxt
    if to not in thread:
        return "a reply must answer the Question or a reply in its thread"
    new = lambda: str(uuid.uuid4())
    r, t = new(), new()
    out = [[r, REPLY, to, text, "str"],
           [t, TODO, question, "Act on the reply to this question: " + (text if len(text) <= 200 else text[:199] + "…"), "str"]
           ] + provenance(person, rows, [r, t])
    return append(home, out)


def provenance(person, rows, handles):
    """Rows saying these statements were written by this person in the Explorer, now."""
    name = next((v for _, _, a, e, v, _ in rows if a == NAME and e == person), person)
    new = lambda: str(uuid.uuid4())
    pv = new()
    return ([[new(), COMP, pv, PROVINFO, "uuid"],
             [new(), NOTE, pv, f"Written by {name} in the Trunky Explorer.", "str"],
             [new(), RECORDED, pv, dt.datetime.now().astimezone().isoformat(timespec="seconds"), "str"]] +
            [[new(), PROV, h, pv, "uuid"] for h in handles])


def write_edit(person, handle, text):
    """Replace one current statement with a new value; returns the appended rows, or the reason it was refused."""
    value, vtype = entry_value(text)
    if value is None:
        return vtype
    with STORE.lock:
        STORE._load()
        rows = STORE.rows
    old = next((r for r in rows if r[1] == handle), None)
    if not old:
        return "this value has changed since the page loaded; reload to see the current one"
    home, _, a, e, v, vt = old
    if value == v and (vtype == "uuid") == (vt == "uuid"):
        return "the value is unchanged"
    groups = {EVERYONE} | {g for _, _, at, g, m, _ in rows if at == MEMBER and m == person}
    if not any(at == EDITOR and en == home and g in groups for _, _, at, en, g, _ in rows):
        return "you are not in this set's editor group"
    new = lambda: str(uuid.uuid4())
    n, x = new(), new()
    out = [[n, a, e, value, vtype], [x, REPLACEMENT, handle, n, "uuid"]] + provenance(person, rows, [n, x])
    return append(home, out)


UUID_ENTRY = re.compile(r"\{\{\s*([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\s*\}\}")


def entry_value(text):
    """(value, value type) for a typed entry, or (None, reason). See the module docstring."""
    text = (text or "").strip()
    if not text or len(text) > MAX_EDIT:
        return None, f"a value must be 1 to {MAX_EDIT} characters"
    if text.startswith("'{{"):
        return text[1:], "str"
    m = UUID_ENTRY.fullmatch(text)
    if m:
        return m.group(1).lower(), "uuid"
    if text.startswith("{{") and text.endswith("}}"):
        return None, "{{...}} must hold a UUID; start with '{{ to store the braces as text"
    return text, "str"


def write_add(person, entity, attribute, text):
    """Give an entity its first value for one of its components' slots; returns the appended rows, or the reason it was refused."""
    value, vtype = entry_value(text)
    if value is None:
        return vtype
    with STORE.lock:
        STORE._load()
        rows = STORE.rows
    comps = {v: s for s, _, a, e, v, _ in rows if a == COMP and e == entity}
    homes = [comps[c] for _, _, a, c, v, _ in rows if a in SLOTS and v == attribute and c in comps]
    if not homes and not any(a == attribute for _, _, a, _, _, _ in rows):
        return "that attribute is neither a slot of this item's components nor used anywhere"
    homes += list(comps.values()) + [s for s, _, a, e, _, _ in rows if a == NAME and e == entity]
    if any(a == attribute and e == entity for _, _, a, e, _, _ in rows):
        return "this item already has a value there; edit that value instead"
    groups = {EVERYONE} | {g for _, _, at, g, m, _ in rows if at == MEMBER and m == person}
    editable = {en for _, _, at, en, g, _ in rows if at == EDITOR and g in groups}
    home = next((h for h in homes if h in editable), None)
    if not home:
        return "you are not in this set's editor group"
    n = str(uuid.uuid4())
    out = [[n, attribute, entity, value, vtype]] + provenance(person, rows, [n])
    return append(home, out)


def write_new(person, component, set_id, name):
    """Make an item carrying one component; returns the appended rows and the new id, or the reason it was refused."""
    value, vtype = entry_value(name)
    if value is None:
        return vtype
    with STORE.lock:
        STORE._load()
        rows = STORE.rows
    if not any(a == COMP and v == component for _, _, a, _, v, _ in rows):
        return "that is not a component in use"
    groups = {EVERYONE} | {g for _, _, at, g, m, _ in rows if at == MEMBER and m == person}
    if not any(at == EDITOR and en == set_id and g in groups for _, _, at, en, g, _ in rows):
        return "you are not in that set's editor group"
    new = lambda: str(uuid.uuid4())
    e, c, n = new(), new(), new()
    out = [[c, COMP, e, component, "uuid"], [n, NAME, e, value, vtype]] + provenance(person, rows, [c, n])
    return append(set_id, out, id=e)


def write_component(person, entity, component):
    """Tag an existing item with one more component; returns the appended rows, or the reason it was refused."""
    with STORE.lock:
        STORE._load()
        rows = STORE.rows
    if not any(a == COMP and v == component for _, _, a, _, v, _ in rows):
        return "that is not a component in use"
    if any(a == COMP and e == entity and v == component for _, _, a, e, v, _ in rows):
        return "this item already has that component"
    groups = {EVERYONE} | {g for _, _, at, g, m, _ in rows if at == MEMBER and m == person}
    editable = {en for _, _, at, en, g, _ in rows if at == EDITOR and g in groups}
    homes = ([s for s, _, a, e, _, _ in rows if a == COMP and e == entity] +
             [s for s, _, a, e, _, _ in rows if a == NAME and e == entity])
    home = next((s for s in homes if s in editable), None)
    if not home:
        return "this item has no component or name in a set you may edit"
    c = str(uuid.uuid4())
    out = [[c, COMP, entity, component, "uuid"]] + provenance(person, rows, [c])
    return append(home, out)


def synced():
    try:
        base = json.loads(SYNC_BASE.read_text())
    except (OSError, ValueError):
        return {}
    return {e: sorted(v) for e, v in base.items() if isinstance(v, dict)}


class Handler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(HERE / "static"), **k)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/synced" and not PUBLIC:
            body = json.dumps(synced()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path != "/api/data":
            if PUBLIC and path not in PUBLIC_PATHS:
                return self.send_error(404)
            return super().do_GET()
        etag, body = STORE.payload(viewer(self.headers))
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Encoding", "gzip")
        self.send_header("ETag", etag)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = self.path.split("?")[0]
        if PUBLIC or path not in ("/api/reply", "/api/edit", "/api/add", "/api/new", "/api/component"):
            return self.send_error(404)
        n = int(self.headers.get("Content-Length") or 0)
        if (not self.headers.get("X-Trunky-Explorer") or "application/json" not in (self.headers.get("Content-Type") or "")
                or not 0 < n <= 20000):
            return self.send_error(400)
        try:
            req = json.loads(self.rfile.read(n))
            if path == "/api/new":
                why = write_new(viewer(self.headers), str(req["component"]), str(req["set"]), str(req["name"]))
            elif path == "/api/component":
                why = write_component(viewer(self.headers), str(req["entity"]), str(req["component"]))
            elif path == "/api/reply":
                why = write_reply(viewer(self.headers), str(req["question"]), str(req["to"]), str(req["text"]))
            elif path == "/api/edit":
                why = write_edit(viewer(self.headers), str(req["handle"]), str(req["text"]))
            else:
                why = write_add(viewer(self.headers), str(req["entity"]), str(req["attribute"]), str(req["text"]))
        except (ValueError, KeyError, TypeError):
            why = "bad request"
        done = why if isinstance(why, dict) else None
        why = None if done else why
        body = json.dumps({"ok": not why, "error": why, **(done or {})}).encode()
        self.send_response(400 if why else 200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--public"]
    port = int(args[0]) if args else 8850
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
