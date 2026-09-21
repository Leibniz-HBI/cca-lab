"""One durable coordinator, bounded request threads. Run as a separate process."""
import csv
import fcntl
import json
import logging
import signal
import threading
import time
from .runtime import timed_batch
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

import httpx

from .db import connect, dumps, heartbeat, init, root
from .llm import classify

log = logging.getLogger("textlab.worker")
stopping = threading.Event()


def import_dataset(dataset):
    did = dataset["id"]
    log.info("dataset_import_started dataset_id=%s", did)
    with connect() as db:
        db.execute("UPDATE datasets SET status='importing',total=0,error=NULL WHERE id=?", (did,))
        db.execute("DELETE FROM records WHERE dataset_id=?", (did,))
    try:
        csv.field_size_limit(10 * 1024 * 1024)
        with open(dataset["path"], encoding=dataset["encoding"], newline="") as source:
            reader = csv.DictReader(source, delimiter=dataset["delimiter"], strict=True)
            columns = reader.fieldnames
            if not columns or any(not c.strip() for c in columns) or len(set(columns)) != len(columns):
                raise ValueError("CSV requires unique, nonempty column names")
            if len(columns) > 10000:
                raise ValueError("Too many columns")
            with connect() as db:
                db.execute("UPDATE datasets SET columns_json=? WHERE id=?", (dumps(columns), did))
            batch, total = [], 0
            for total, row in enumerate(reader, 1):
                if None in row or any(v is None for v in row.values()):
                    raise ValueError(f"Inconsistent column count at record {total}")
                batch.append((did, total, dumps(row)))
                if len(batch) >= 500:
                    save_import(did, batch, total)
                    batch.clear()
                    if stopping.is_set():
                        return  # status importing: import restarts safely after reboot
            save_import(did, batch, total)
            with connect() as db:
                db.execute("UPDATE datasets SET status='ready',total=? WHERE id=?", (total, did))
        log.info("dataset_import_completed dataset_id=%s rows=%s", did, total)
    except Exception as exc:
        log.warning("dataset_import_failed dataset_id=%s error_type=%s", did, type(exc).__name__)
        with connect() as db:
            db.execute("UPDATE datasets SET status='failed',error=? WHERE id=?", (str(exc)[:1000], did))


def save_import(did, batch, total):
    log.debug("dataset_import_progress dataset_id=%s rows=%s", did, total)
    with connect() as db:
        db.executemany("INSERT INTO records VALUES(?,?,?)", batch)
        db.execute("UPDATE datasets SET total=? WHERE id=?", (total, did))


def save_result(job_id, row_no, result):
    log.log(logging.WARNING if result["status"] != "ok" else logging.DEBUG,
            "classification_result job_id=%s row=%s status=%s attempts=%s seconds=%s",
            job_id, row_no, result["status"], result["attempts"], result["seconds"])
    with connect() as db:
        inserted = db.execute("INSERT OR IGNORE INTO results(job_id,row_no,labels,rationale,status,error,raw,attempts,seconds,prompt_tokens,completion_tokens,evidence,thinking,attempt_outputs,error_count,self_reported_confidence,alternative_interpretations,candidate_interpretations) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            job_id, row_no, dumps(result["labels"]), result["rationale"], result["status"], result["error"], result["raw"],
            result["attempts"], result["seconds"], result["prompt_tokens"], result["completion_tokens"], dumps(result.get("evidence", [])), result.get("thinking"), dumps(result.get("attempt_outputs", [])), max(int(bool(result["error"])),sum(bool(a.get("error")) for a in result.get("attempt_outputs", []))), result.get("self_reported_confidence"), dumps(result.get("alternative_interpretations", [])), dumps(result.get("candidate_interpretations", [])))).rowcount
        if inserted:
            db.execute("UPDATE jobs SET done=done+1,failed=failed+?,fallback_count=fallback_count+?,updated=?,last_error=COALESCE(?,last_error),requests=requests+?,prompt_tokens=prompt_tokens+?,completion_tokens=completion_tokens+?,total_seconds=total_seconds+? WHERE id=?", (
                int(result["status"] != "ok"), int(result["status"] == "fallback"), time.time(), result["error"], (0 if result.get("accounted") else result["attempts"]), result["prompt_tokens"], result["completion_tokens"], (0 if result.get("accounted") else result["seconds"]), job_id))


def run_batch(job):
    log.debug("job_batch job_id=%s cursor=%s", job["id"], job["cursor"])
    snap = json.loads(job["snapshot"])
    if snap.get("prompt_protocol")=="experiment-v3":
        from .executor import run_window
        return run_window(job,stopping,save_result)
    concurrency = snap["query"]["concurrency"]
    # Cursor is committed only after the whole bounded window has settled.
    # Crash recovery skips already committed results inside this window.
    with connect() as db:
        rows = db.execute("SELECT row_no,data FROM records WHERE dataset_id=? AND row_no>? ORDER BY row_no LIMIT ?", (
            job["dataset_id"], job["cursor"], concurrency)).fetchall()
        completed = {r[0] for r in db.execute("SELECT row_no FROM results WHERE job_id=? AND row_no>? AND row_no<=?", (
            job["id"], job["cursor"], rows[-1]["row_no"] if rows else job["cursor"]))}
    if not rows:
        log.info("job_finished job_id=%s done=%s failed=%s", job["id"], job["done"], job["failed"])
        with connect() as db:
            db.execute("UPDATE jobs SET status=CASE WHEN failed>0 THEN 'completed_with_errors' ELSE 'completed' END,updated=?,finished_at=? WHERE id=? AND status='running'", (time.time(), time.time(), job["id"]))
        return
    with httpx.Client(trust_env=False, limits=httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)) as client:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {}
            all_submitted = True
            for row in rows:
                if row["row_no"] in completed:
                    continue
                with connect() as db:
                    status = db.execute("SELECT status FROM jobs WHERE id=?", (job["id"],)).fetchone()[0]
                if stopping.is_set() or status != "running":
                    all_submitted = False
                    break
                text = json.loads(row["data"]).get(snap["text_column"])
                futures[pool.submit(classify, snap, text, client)] = row["row_no"]
            while futures:
                finished, _ = wait(futures, timeout=1, return_when=FIRST_COMPLETED)
                for future in finished:
                    row_no = futures.pop(future)
                    save_result(job["id"], row_no, future.result())
    if all_submitted:
        with connect() as db:
            db.execute("UPDATE jobs SET cursor=?,updated=? WHERE id=?", (rows[-1]["row_no"], time.time(), job["id"]))


def tick():
    with connect() as db:
        db.execute("UPDATE jobs SET status=CASE status WHEN 'pausing' THEN 'paused' ELSE 'cancelled' END,finished_at=CASE WHEN status='cancelling' THEN ? ELSE finished_at END,updated=? WHERE status IN ('pausing','cancelling')", (time.time(),time.time()))
        dataset = db.execute("SELECT * FROM datasets WHERE status IN ('uploaded','importing') ORDER BY created LIMIT 1").fetchone()
    from .evaluation import finalize_one
    if finalize_one():
        return True
    from .prediction import finalize_prediction
    if finalize_prediction():
        return True
    if dataset:
        import_dataset(dict(dataset))
        return True
    with connect() as db:
        job = db.execute("SELECT * FROM jobs WHERE status IN ('queued','running') ORDER BY created LIMIT 1").fetchone()
        if job:
            db.execute("UPDATE jobs SET status='running',updated=? WHERE id=? AND status='queued'", (time.time(), job["id"]))
    if job:
        if job["status"] == "queued":
            log.info("job_started job_id=%s total=%s", job["id"], job["total"])
        try:
            timed_batch(dict(job), run_batch)
        except Exception:
            log.exception("Job worker error for %s", job["id"])
            with connect() as db:
                db.execute("UPDATE jobs SET status='paused',last_error='Internal worker error; check server log',updated=? WHERE id=? AND status='running'", (time.time(), job["id"]))
        return True
    return False


def pulse():
    while not stopping.is_set():
        heartbeat()
        stopping.wait(2)


def recover_interrupted_work():
    with connect() as db:
        db.execute("UPDATE jobs SET runtime_complete=0,active_since=NULL WHERE active_since IS NOT NULL")
        db.execute("UPDATE llm_requests SET status='interrupted',output_json=? WHERE status='running'", (dumps({"error":"Worker interrupted; request outcome unknown"}),))
        db.execute("UPDATE predictions SET artifact_status='pending' WHERE artifact_status='building'")


def main():
    from .logging_config import configure_logging
    configure_logging()
    init()
    lock = open(root() / "worker.lock", "a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("A worker is already running for this data directory")
    recover_interrupted_work()
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    thread = threading.Thread(target=pulse, daemon=True)
    thread.start()
    log.info("Worker ready")
    while not stopping.is_set():
        if not tick():
            stopping.wait(0.5)
    thread.join(timeout=3)
    lock.close()


if __name__ == "__main__":
    main()
