import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


def root():
    path = Path(os.environ.get("TEXTLAB_DATA", "data")).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def uid():
    return uuid.uuid4().hex


def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


@contextmanager
def connect():
    db = sqlite3.connect(root() / "textlab.sqlite", timeout=30)
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


def init():
    with connect() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript('''
        CREATE TABLE IF NOT EXISTS tasks (
          id TEXT PRIMARY KEY, revision INTEGER NOT NULL, spec TEXT NOT NULL, updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS profiles (
          id TEXT PRIMARY KEY, spec TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS datasets (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL, bytes INTEGER NOT NULL,
          delimiter TEXT NOT NULL, encoding TEXT NOT NULL, status TEXT NOT NULL,
          columns_json TEXT NOT NULL DEFAULT '[]', total INTEGER NOT NULL DEFAULT 0,
          error TEXT, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS records (
          dataset_id TEXT NOT NULL REFERENCES datasets(id), row_no INTEGER NOT NULL,
          data TEXT NOT NULL, PRIMARY KEY(dataset_id,row_no)) WITHOUT ROWID;
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, dataset_id TEXT NOT NULL REFERENCES datasets(id),
          snapshot TEXT NOT NULL, status TEXT NOT NULL, total INTEGER NOT NULL,
          done INTEGER NOT NULL DEFAULT 0, failed INTEGER NOT NULL DEFAULT 0,
          cursor INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL, updated REAL NOT NULL,
          last_error TEXT, requests INTEGER NOT NULL DEFAULT 0,
          prompt_tokens INTEGER NOT NULL DEFAULT 0, completion_tokens INTEGER NOT NULL DEFAULT 0,
          total_seconds REAL NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS results (
          job_id TEXT NOT NULL REFERENCES jobs(id), row_no INTEGER NOT NULL,
          labels TEXT NOT NULL, rationale TEXT, status TEXT NOT NULL, error TEXT,
          raw TEXT, attempts INTEGER NOT NULL, seconds REAL NOT NULL,
          prompt_tokens INTEGER NOT NULL, completion_tokens INTEGER NOT NULL,
          PRIMARY KEY(job_id,row_no)) WITHOUT ROWID;
        CREATE TABLE IF NOT EXISTS worker_state (
          id INTEGER PRIMARY KEY CHECK(id=1), heartbeat REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS gold_sets (
          id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL REFERENCES datasets(id),
          spec TEXT NOT NULL, total INTEGER NOT NULL, label_counts TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS gold_rows (
          gold_id TEXT NOT NULL REFERENCES gold_sets(id), row_no INTEGER NOT NULL,
          doc_id TEXT NOT NULL, labels TEXT NOT NULL,
          PRIMARY KEY(gold_id,row_no), UNIQUE(gold_id,doc_id)) WITHOUT ROWID;
        CREATE TABLE IF NOT EXISTS evaluations (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, gold_id TEXT NOT NULL REFERENCES gold_sets(id),
          task_snapshot TEXT NOT NULL, created REAL NOT NULL,
          report_json TEXT, report_error TEXT);
        CREATE TABLE IF NOT EXISTS evaluation_runs (
          evaluation_id TEXT NOT NULL REFERENCES evaluations(id),
          job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id), name TEXT NOT NULL, ordinal INTEGER NOT NULL,
          PRIMARY KEY(evaluation_id,job_id)) WITHOUT ROWID;
        CREATE TABLE IF NOT EXISTS predictions (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, dataset_id TEXT NOT NULL REFERENCES datasets(id),
          created REAL NOT NULL, artifact_status TEXT NOT NULL DEFAULT 'pending', artifact_error TEXT);
        CREATE TABLE IF NOT EXISTS prediction_runs (
          prediction_id TEXT NOT NULL REFERENCES predictions(id), job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id),
          task_name TEXT NOT NULL, ordinal INTEGER NOT NULL, PRIMARY KEY(prediction_id,job_id)) WITHOUT ROWID;
        CREATE TABLE IF NOT EXISTS prediction_artifacts (
          prediction_id TEXT NOT NULL REFERENCES predictions(id), format TEXT NOT NULL,
          path TEXT NOT NULL, bytes INTEGER NOT NULL, PRIMARY KEY(prediction_id,format)) WITHOUT ROWID;
        ''')
        # Additive, serialized migration from 0.1. API and worker may start together.
        db.execute("BEGIN IMMEDIATE")
        columns = {r[1] for r in db.execute("PRAGMA table_info(results)")}
        for name, definition in {"evidence": "TEXT NOT NULL DEFAULT '[]'", "thinking": "TEXT", "attempt_outputs": "TEXT NOT NULL DEFAULT '[]'"}.items():
            if name not in columns:
                db.execute(f"ALTER TABLE results ADD COLUMN {name} {definition}")
        old_jobs = {r[1] for r in db.execute("PRAGMA table_info(jobs)")}
        for name, definition in {"started_at":"REAL", "finished_at":"REAL", "active_seconds":"REAL NOT NULL DEFAULT 0", "active_since":"REAL", "runtime_complete":"INTEGER NOT NULL DEFAULT 0"}.items():
            if name not in old_jobs:
                db.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")
        if "active_seconds" not in old_jobs:
            db.execute("UPDATE evaluations SET report_json=NULL,report_error=NULL")
        result_columns = {r[1] for r in db.execute("PRAGMA table_info(results)")}
        if 'error_count' not in result_columns:
            db.execute("ALTER TABLE results ADD COLUMN error_count INTEGER NOT NULL DEFAULT 0")
            db.execute("UPDATE results SET error_count=MAX(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END, (SELECT COUNT(*) FROM json_each(results.attempt_outputs) WHERE json_extract(value,'$.error') IS NOT NULL))")
            db.execute("UPDATE evaluations SET report_json=NULL,report_error=NULL")
        db.execute("CREATE INDEX IF NOT EXISTS result_errors ON results(job_id,row_no) WHERE error_count>0")
        if 'fallback_count' not in old_jobs:
            db.execute("ALTER TABLE jobs ADD COLUMN fallback_count INTEGER NOT NULL DEFAULT 0")
        db.execute("PRAGMA user_version=4")


def heartbeat():
    with connect() as db:
        db.execute("INSERT INTO worker_state VALUES(1,?) ON CONFLICT(id) DO UPDATE SET heartbeat=excluded.heartbeat", (time.time(),))
