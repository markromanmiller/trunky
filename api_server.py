#!/usr/bin/env python3
"""HTTP API over lignin.db. Bind to 127.0.0.1 only -- Caddy is the sole
ingress and handles TLS + Basic Auth. This process does no auth itself.

Additive-only is enforced structurally: the only mutating route is
POST /statements, which always INSERTs a new row with a freshly minted
handle. There is no route that can UPDATE or DELETE an existing row.
"""
import difflib
import json
import re
import sqlite3
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from sentence_transformers import SentenceTransformer

import vector_store
from paths import DB_PATH, EXPLORER_PATH, OPENAPI_PATH, LLMS_TXT_PATH

HOST, PORT = "127.0.0.1", 8300

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
VALUE_TYPES = {"uuid", "str", "int"}

A_COMPONENT = "90c2b9bb-ff6b-4f84-a29b-7b9e8dcfe04a"
THE_PROVENANCE = "d9496c5d-6e55-43ca-84bf-72d565c33419"
THE_INTENTION = "9ca34038-1a65-4ede-88c5-1492ab4bc249"

print(f"loading embedding model {vector_store.MODEL_NAME}...")
MODEL = SentenceTransformer(vector_store.MODEL_NAME, device="cpu")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

ROW_LIMIT = 5000

def query_rows(conn, sql, params, limit=ROW_LIMIT):
    """Run a SELECT with a LIMIT+1 probe so callers can tell a full result
    apart from one truncated by the row cap, without a separate COUNT(*)."""
    rows = [dict(r) for r in conn.execute(sql + " LIMIT ?", (*params, limit + 1))]
    truncated = len(rows) > limit
    return rows[:limit], truncated

def index_intentions(items):
    """items: iterable of (handle, entity, value) for rows whose attribute is
    theIntention. Embeds and upserts them into vectors.db, keeping the
    semantic index live as writes come in through this server."""
    items = list(items)
    if not items:
        return
    texts = [value for _, _, value in items]
    vectors = MODEL.encode(texts, normalize_embeddings=True)
    conn = vector_store.get_conn()
    for (handle, entity, value), vec in zip(items, vectors):
        vector_store.upsert(conn, handle, entity, value, vec)
    conn.close()

def validate_item(item):
    """Check one {attribute, entity, value, value_type} dict. Returns an error
    string, or None if the item is well-formed."""
    if not isinstance(item, dict):
        return "statement must be an object"
    for field in ("attribute", "entity", "value", "value_type"):
        if field not in item:
            return f"missing field: {field}"
    value_type = item["value_type"]
    if value_type not in VALUE_TYPES:
        return f"value_type must be one of {sorted(VALUE_TYPES)}"
    if value_type == "uuid" and not UUID_RE.match(item["value"]):
        return "value_type is uuid but value is not a UUID"
    for field_name in ("attribute", "entity"):
        if not UUID_RE.match(item[field_name]):
            return f"{field_name} must be a UUID"
    return None

class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status, payload, extra_headers=None):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path in ("/", "/explorer"):
            body = EXPLORER_PATH.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/openapi.yaml":
            body = OPENAPI_PATH.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/yaml; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/llms.txt":
            body = LLMS_TXT_PATH.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/statements/search":
            self._get_search(parsed)
            return

        if parsed.path == "/statements/semantic-search":
            self._get_semantic_search(parsed)
            return

        if parsed.path == "/statements/by-component":
            self._get_by_component(parsed)
            return

        if parsed.path != "/statements":
            self._send_json(404, {"error": "not found"})
            return

        qs = parse_qs(parsed.query)
        clauses, params = [], []
        for field in ("attribute", "entity", "value", "handle"):
            if field in qs:
                clauses.append(f"{field} = ?")
                params.append(qs[field][0])

        sql = "SELECT handle, attribute, entity, value, value_type FROM statements"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)

        conn = get_conn()
        rows, truncated = query_rows(conn, sql, params)
        conn.close()
        self._send_json(200, rows, {"X-Truncated": "true" if truncated else "false"})

    def _get_search(self, parsed):
        qs = parse_qs(parsed.query)
        query = qs.get("q", [None])[0]
        if not query:
            self._send_json(400, {"error": "missing query param: q"})
            return
        attribute = qs.get("attribute", [None])[0]
        try:
            limit = int(qs.get("limit", ["20"])[0])
        except ValueError:
            self._send_json(400, {"error": "limit must be an integer"})
            return

        sql = "SELECT handle, attribute, entity, value, value_type FROM statements WHERE value_type = 'str'"
        params = []
        if attribute:
            sql += " AND attribute = ?"
            params.append(attribute)

        conn = get_conn()
        candidates = [dict(r) for r in conn.execute(sql, params)]
        conn.close()

        ql = query.lower()
        scored = []
        for r in candidates:
            v = r["value"].lower()
            score = 1.0 if v == ql else difflib.SequenceMatcher(None, ql, v).ratio()
            if ql in v:
                score = max(score, 0.9)
            if score >= 0.3:
                scored.append((score, r))
        scored.sort(key=lambda pair: -pair[0])

        results = [dict(r, score=round(s, 3)) for s, r in scored[:limit]]
        self._send_json(200, {"matches": results, "total": len(scored)})

    def _get_by_component(self, parsed):
        qs = parse_qs(parsed.query)
        component = qs.get("component", [None])[0]
        if not component or not UUID_RE.match(component):
            self._send_json(400, {"error": "missing or malformed query param: component"})
            return

        conn = get_conn()
        sql = (
            "SELECT handle, attribute, entity, value, value_type FROM statements "
            "WHERE entity IN (SELECT entity FROM statements WHERE attribute = ? AND value = ?)"
        )
        rows, truncated = query_rows(conn, sql, (A_COMPONENT, component))
        conn.close()
        self._send_json(200, rows, {"X-Truncated": "true" if truncated else "false"})

    def _get_semantic_search(self, parsed):
        qs = parse_qs(parsed.query)
        query = qs.get("q", [None])[0]
        if not query:
            self._send_json(400, {"error": "missing query param: q"})
            return
        try:
            limit = int(qs.get("limit", ["10"])[0])
        except ValueError:
            self._send_json(400, {"error": "limit must be an integer"})
            return

        qvec = MODEL.encode([query], normalize_embeddings=True)[0]
        conn = vector_store.get_conn()
        results = vector_store.search(conn, qvec, limit)
        conn.close()

        matches = [
            {"score": round(score, 3), "handle": handle, "entity": entity, "value": text}
            for score, handle, entity, text in results
        ]
        self._send_json(200, {"matches": matches})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/statements":
            self._post_single()
        elif path == "/statements/bulk":
            self._post_bulk()
        else:
            self._send_json(404, {"error": "not found"})

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length))

    def _post_single(self):
        try:
            body = self._read_json_body()
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid JSON body"})
            return

        error = validate_item(body)
        if error:
            self._send_json(400, {"error": error})
            return

        attribute, entity, value, value_type = (
            body["attribute"], body["entity"], body["value"], body["value_type"]
        )
        provenance = body.get("provenance")

        conn = get_conn()
        handle = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO statements (handle, attribute, entity, value, value_type) VALUES (?, ?, ?, ?, ?)",
            (handle, attribute, entity, value, value_type),
        )
        response = {"handle": handle, "attribute": attribute, "entity": entity,
                    "value": value, "value_type": value_type}
        if provenance is not None:
            provenance_handle = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO statements (handle, attribute, entity, value, value_type) VALUES (?, ?, ?, ?, ?)",
                (provenance_handle, THE_PROVENANCE, handle, provenance, "uuid"),
            )
            response["provenance"] = provenance
            response["provenance_handle"] = provenance_handle
        conn.commit()
        conn.close()
        if attribute == THE_INTENTION:
            index_intentions([(handle, entity, value)])
        self._send_json(201, response)

    def _post_bulk(self):
        try:
            body = self._read_json_body()
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid JSON body"})
            return

        if "statements" not in body or not isinstance(body["statements"], list):
            self._send_json(400, {"error": "missing or non-array field: statements"})
            return
        if len(body["statements"]) == 0:
            self._send_json(400, {"error": "statements must not be empty"})
            return

        provenance = body.get("provenance")
        items = body["statements"]

        # Validate every item before writing anything -- all-or-nothing.
        for i, item in enumerate(items):
            error = validate_item(item)
            if error:
                self._send_json(400, {"error": error, "index": i})
                return

        conn = get_conn()
        results = []
        for item in items:
            handle = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO statements (handle, attribute, entity, value, value_type) VALUES (?, ?, ?, ?, ?)",
                (handle, item["attribute"], item["entity"], item["value"], item["value_type"]),
            )
            result = {"handle": handle, "attribute": item["attribute"], "entity": item["entity"],
                      "value": item["value"], "value_type": item["value_type"]}
            if provenance is not None:
                provenance_handle = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO statements (handle, attribute, entity, value, value_type) VALUES (?, ?, ?, ?, ?)",
                    (provenance_handle, THE_PROVENANCE, handle, provenance, "uuid"),
                )
                result["provenance"] = provenance
                result["provenance_handle"] = provenance_handle
            results.append(result)
        conn.commit()
        conn.close()
        index_intentions(
            (r["handle"], r["entity"], r["value"]) for r in results if r["attribute"] == THE_INTENTION
        )
        self._send_json(201, results)

    def do_PUT(self):
        self._send_json(405, {"error": "statements are append-only; PUT is not supported"})

    def do_DELETE(self):
        self._send_json(405, {"error": "statements are append-only; DELETE is not supported"})

    def log_message(self, fmt, *args):
        pass

if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"lignin API listening on http://{HOST}:{PORT}")
    server.serve_forever()
