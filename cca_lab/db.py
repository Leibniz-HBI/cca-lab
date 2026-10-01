from contextvars import ContextVar

project_root = ContextVar("project_root", default=None)

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


def root():
    path = (project_root.get() or Path(os.environ.get("CCA_LAB_DATA", "data"))).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def uid():
    return uuid.uuid4().hex


def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


@contextmanager
def connect():
    db = sqlite3.connect(root() / "cca_lab.sqlite", timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=30000")
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


SCHEMA_VERSION = 7
SCHEMA = Path(__file__).with_name("schema.sql").read_text()


def schema_signature(db):
    """Compare table definitions and indexes without reading application data."""
    tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    return {name: (tuple(tuple(r) for r in db.execute('SELECT * FROM pragma_table_info(?)', (name,))),
                   tuple(tuple(r) for r in db.execute('SELECT * FROM pragma_foreign_key_list(?)', (name,))),
                   tuple(sorted((r[1], r[2], r[3], r[4]) for r in db.execute('SELECT * FROM pragma_index_list(?)', (name,)))))
            for name in tables}


def init():
    with connect() as db:
        # Serialize API/worker startup, including the empty-database check.
        db.execute("BEGIN IMMEDIATE")
        version = db.execute("PRAGMA user_version").fetchone()[0]
        populated = db.execute("SELECT 1 FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' LIMIT 1").fetchone()
        if not populated and version == 0:
            for statement in SCHEMA.split(';'):
                if statement.strip():
                    db.execute(statement)
            db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        else:
            with sqlite3.connect(":memory:") as expected:
                expected.executescript(SCHEMA)
                valid = version == SCHEMA_VERSION and schema_signature(db) == schema_signature(expected)
            if not valid:
                raise RuntimeError("Unsupported CCA-Lab database schema; startup stopped without changing application data. Use a current database or an empty data directory.")
        db.commit()
        db.execute("PRAGMA journal_mode=WAL")


def heartbeat():
    with connect() as db:
        db.execute("INSERT INTO worker_state VALUES(1,?) ON CONFLICT(id) DO UPDATE SET heartbeat=excluded.heartbeat", (time.time(),))
