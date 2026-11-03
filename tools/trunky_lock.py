"""One lock for every process that writes Trunky sets (paug_sync, the ECS engine, one-off scripts).

    from trunky_lock import write_lock
    with write_lock():            # exits if another writer holds it
        ...
    with write_lock(wait=True):   # blocks until it is free
        ...

The lock is an flock on state/trunky-write.lock, so it is released when the process exits,
even after a crash.
"""
import contextlib, fcntl, sys
from pathlib import Path

LOCK_PATH = Path(__file__).resolve().parent.parent / "state" / "trunky-write.lock"


@contextlib.contextmanager
def write_lock(wait=False, who=""):
    LOCK_PATH.parent.mkdir(exist_ok=True)
    with open(LOCK_PATH, "a+") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        except BlockingIOError:
            f.seek(0)
            holder = f.read().strip() or "another writer"
            sys.exit(f"Trunky is locked by {holder}; not running")
        f.seek(0); f.truncate(); f.write(who or Path(sys.argv[0]).name); f.flush()
        try:
            yield
        finally:
            f.seek(0); f.truncate(); f.flush()
            fcntl.flock(f, fcntl.LOCK_UN)
