"""Shared cache logic for the theIntention semantic index (vectors.db).

Derived data, not source of truth -- rebuildable at any time from lignin.db
via embed_intentions.py. api_server.py keeps it live-updated on every write
that touches theIntention; this module is the one place that knows the
schema and the cosine-similarity search, so all three callers (the live
server, the bulk rebuild script, and the standalone CLI) stay in sync.
"""
import sqlite3
import time

import numpy as np

from paths import VECTORS_DB

MODEL_NAME = "all-MiniLM-L6-v2"

SCHEMA = """
CREATE TABLE IF NOT EXISTS intention_vectors (
    handle TEXT PRIMARY KEY,   -- the theIntention statement's own handle
    entity TEXT NOT NULL,      -- the concept this intention describes
    text TEXT NOT NULL,
    model TEXT NOT NULL,
    embedded_at TEXT NOT NULL,
    vector BLOB NOT NULL       -- float32 numpy array, tobytes()
);
CREATE INDEX IF NOT EXISTS idx_intention_vectors_entity ON intention_vectors(entity);
"""

def get_conn():
    conn = sqlite3.connect(VECTORS_DB)
    conn.executescript(SCHEMA)
    return conn

def upsert(conn, handle, entity, text, vector):
    conn.execute(
        "INSERT OR REPLACE INTO intention_vectors (handle, entity, text, model, embedded_at, vector) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (handle, entity, text, MODEL_NAME, time.strftime("%Y-%m-%dT%H:%M:%S"),
         np.asarray(vector, dtype=np.float32).tobytes()),
    )
    conn.commit()

def search(conn, qvec, limit=20):
    """qvec must already be normalized, same as the stored vectors."""
    rows = conn.execute("SELECT handle, entity, text, vector FROM intention_vectors").fetchall()
    scored = []
    for handle, entity, text, blob in rows:
        v = np.frombuffer(blob, dtype=np.float32)
        score = float(np.dot(qvec, v))
        scored.append((score, handle, entity, text))
    scored.sort(key=lambda row: -row[0])
    return scored[:limit]
