"""Shared filesystem paths for lignindb.

Resolved relative to this file's own location, so the repo works when cloned
anywhere without editing hardcoded paths. DB_PATH and VECTORS_DB can still be
overridden via environment variables for a deployment that wants its data
somewhere else (e.g. a separate public-facing instance).
"""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

DB_PATH = os.environ.get("LIGNIN_DB_PATH", str(REPO_ROOT / "lignin.db"))
VECTORS_DB = os.environ.get("LIGNIN_VECTORS_DB", str(REPO_ROOT / "vectors.db"))
EXPLORER_PATH = REPO_ROOT / "explorer.html"
OPENAPI_PATH = REPO_ROOT / "openapi.yaml"
LLMS_TXT_PATH = REPO_ROOT / "llms.txt"
