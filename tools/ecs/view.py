"""The current-statements view the ECS engine queries (proposals/ecs-engine-design.md).

Current = every statement in every set, minus: statements replaced by aReplacement, statements and
entities named by anErratum, statements and entities whose theRemovalTime has passed, and ""-valued rows. The engine runs as the owner, so permissions don't
filter anything yet. Each statement becomes one RDF triple <urn:uuid:entity> <urn:uuid:attribute> value,
with uuid values as IRIs and everything else as plain literals.
"""
import csv, datetime as dt, os
from pathlib import Path

from rdflib import Graph, Literal, URIRef

ROOT = Path(__file__).resolve().parents[2]
COMP = "90c2b9bb-ff6b-4f84-a29b-7b9e8dcfe04a"
REPLACEMENT = "8f9dc95b-c4d3-4500-9a6c-9ddc63cdecf9"
ERRATUM = "1c260a46-c907-4efc-adb2-9345aebd9500"
REMOVAL_TIME = "7ede6e59-945b-4a85-94d8-cce67bf154cc"


def conf(key, default=None, many=False):
    """A setting from trunky.conf (`key = value` lines; see trunky.conf.example). Paths are given with ~
    expanded. many=True returns every value for a key that may repeat."""
    vals = []
    path = ROOT / "trunky.conf"
    if path.exists():
        for line in path.read_text().splitlines():
            k, sep, v = line.partition("=")
            if sep and not line.lstrip().startswith("#") and k.strip() == key and v.strip():
                vals.append(os.path.expanduser(v.strip()))
    return vals if many else (vals[0] if vals else default)


def _passed(t):
    try:
        when = dt.datetime.fromisoformat(t)
    except ValueError:
        return False
    if when.tzinfo is None:
        when = when.astimezone()
    return when <= dt.datetime.now().astimezone()


def iri(u):
    return URIRef(f"urn:uuid:{u}")


def uuid_of(term):
    return str(term).removeprefix("urn:uuid:")


def current(rows):
    """The current rows of (set_id, handle, attribute, entity, value, value_type) rows."""
    replaced = {r[3] for r in rows if r[2] == REPLACEMENT}
    errata = {r[3] for r in rows if r[2] == ERRATUM}
    errata |= {r[3] for r in rows if r[2] == REMOVAL_TIME and r[1] not in replaced and _passed(r[4])}
    return [r for r in rows if r[4] != "" and r[1] not in replaced and r[1] not in errata and r[3] not in errata]


class View:
    def __init__(self, root=ROOT):
        self.rows = []      # (set_id, handle, attribute, entity, value, value_type)
        for path in sorted((root / "sets").glob("*.csv")):
            with open(path, newline="", encoding="utf-8") as f:
                for r in list(csv.reader(f))[1:]:
                    if len(r) >= 5:
                        self.rows.append((path.stem, *r[:5]))
        self.current = current(self.rows)
        self.graph = Graph()
        for _, _, a, e, v, vt in self.current:
            self.graph.add((iri(e), iri(a), iri(v) if vt == "uuid" else Literal(v)))
        # an entity's home set: where its first aComponent statement lives
        self.home = {}
        for s, _, a, e, *_ in self.current:
            if a == COMP:
                self.home.setdefault(e, s)

    def query(self, sparql):
        """Rows as dicts of variable -> str (IRIs come back as bare uuids)."""
        res = self.graph.query(sparql)
        return [{str(k): (uuid_of(v) if isinstance(v, URIRef) else str(v)) for k, v in zip(res.vars, row)
                 if v is not None} for row in res]

    def values(self, entity, attribute):
        return [r[4] for r in self.current if r[3] == entity and r[2] == attribute]
