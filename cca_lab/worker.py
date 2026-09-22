"""One durable coordinator, bounded request threads. Run as a separate process."""
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit
import csv
import fcntl
import json
import logging
import signal
import threading
import time
from .runtime import timed_batch


from .db import connect, dumps, heartbeat, init, root

log = logging.getLogger("cca_lab.worker")
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
            db.execute("UPDATE jobs SET done=done+1,failed=failed+?,fallback_count=fallback_count+?,updated=?,last_error=COALESCE(?,last_error) WHERE id=?", (
                int(result["status"] != "ok"), int(result["status"] == "fallback"), time.time(), result["error"], job_id))


def run_batch(job):
    log.debug("job_batch job_id=%s cursor=%s", job["id"], job["cursor"])
    from .executor import run_window
    return run_window(job,stopping,save_result)


def endpoint_key(job):
    """Serialize profiles pointing at the same HTTP origin (including API aliases)."""
    profile = json.loads(job["snapshot"])["profile"]
    url = urlsplit(profile["base_url"])
    return (url.scheme.lower(), (url.hostname or "").lower(),
            url.port or (443 if url.scheme.lower() == "https" else 80))


def execute_window(job):
    try:
        timed_batch(job, run_batch)
    except Exception:
        log.exception("Job worker error for %s", job["id"])
        with connect() as db:
            db.execute("UPDATE jobs SET status='paused',last_error='Internal worker error; check server log',updated=? WHERE id=? AND status='running'", (time.time(), job["id"]))


class ConnectionScheduler:
    """One in-flight window per server; keep request concurrency inside each job."""
    def __init__(self, max_connections=8):
        self.pool = ThreadPoolExecutor(max_workers=max_connections, thread_name_prefix="connection")
        self.limit = max_connections
        self.active = {}

    def reap(self):
        for key, (job_id, future) in list(self.active.items()):
            if future.done():
                future.result()
                del self.active[key]

    def dispatch(self):
        if stopping.is_set():
            return False
        dispatched = False
        # The coordinator alone claims jobs. Commit before starting a request thread.
        with connect() as db:
            jobs = [dict(j) for j in db.execute("SELECT * FROM jobs WHERE status IN ('queued','running') ORDER BY created,id")]
        for job in jobs:
            if len(self.active) >= self.limit:
                break
            key = endpoint_key(job)
            if key in self.active:
                continue
            with connect() as db:
                changed = db.execute("UPDATE jobs SET status='running',updated=? WHERE id=? AND status IN ('queued','running')", (time.time(), job['id'])).rowcount
            if not changed:
                continue
            if job['status'] == 'queued':
                log.info("job_started job_id=%s endpoint=%s total=%s", job['id'], key, job['total'])
            log.debug("job_window_dispatched job_id=%s endpoint=%s", job['id'], key)
            self.active[key] = (job['id'], self.pool.submit(execute_window, job))
            dispatched = True
        return dispatched

    def close(self):
        self.pool.shutdown(wait=True)


def tick(scheduler=None):
    if scheduler:
        scheduler.reap()
    active_ids = [job_id for job_id, _ in scheduler.active.values()] if scheduler else []
    with connect() as db:
        db.execute("UPDATE jobs SET status=CASE status WHEN 'pausing' THEN 'paused' ELSE 'cancelled' END,finished_at=CASE WHEN status='cancelling' THEN ? ELSE finished_at END,updated=? WHERE status IN ('pausing','cancelling')" + (" AND id NOT IN (" + ",".join("?" for _ in active_ids) + ")" if active_ids else ""), (time.time(),time.time(),*active_ids))
        dataset = db.execute("SELECT * FROM datasets WHERE status IN ('uploaded','importing') ORDER BY created LIMIT 1").fetchone()
    dispatched = scheduler.dispatch() if scheduler else False
    from .evaluation import finalize_one
    if finalize_one():
        return True
    from .prediction import finalize_prediction
    if finalize_prediction():
        return True
    if dataset:
        import_dataset(dict(dataset))
        return True
    if scheduler:
        return dispatched
    with connect() as db:
        job = db.execute("SELECT * FROM jobs WHERE status IN ('queued','running') ORDER BY created LIMIT 1").fetchone()
        if job:
            db.execute("UPDATE jobs SET status='running',updated=? WHERE id=? AND status='queued'", (time.time(), job["id"]))
    if job:
        if job["status"] == "queued":
            log.info("job_started job_id=%s total=%s", job["id"], job["total"])
        execute_window(dict(job))
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
    scheduler = ConnectionScheduler()
    try:
        while not stopping.is_set():
            if not tick(scheduler):
                stopping.wait(0.1)
    finally:
        stopping.set()
        scheduler.close()  # Drain requests before releasing the process lock.
        thread.join(timeout=3)
        lock.close()


if __name__ == "__main__":
    main()
