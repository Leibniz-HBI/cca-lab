import csv
import io
import json
import os
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from .db import connect, dumps, init, root, uid
from .llm import available_models, messages
from .models import Task, Profile, NewJob, Query
from .jobs import enqueue, snapshot_for


@asynccontextmanager
async def lifespan(app):
    init()
    yield


app = FastAPI(title="TextLab", version="0.2.0", lifespan=lifespan)


def get(db, table, id):
    # table is always a hard-coded internal identifier.
    row = db.execute(f"SELECT * FROM {table} WHERE id=?", (id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Nicht gefunden")
    return dict(row)


def spec_row(row):
    result = dict(row)
    result["spec"] = json.loads(result["spec"])
    return result


@app.get("/api/health")
def health():
    with connect() as db:
        row = db.execute("SELECT heartbeat FROM worker_state WHERE id=1").fetchone()
    return {"api": "ok", "worker_online": bool(row and time.time() - row[0] < 15)}


@app.get("/api/tasks")
def tasks():
    with connect() as db:
        return [spec_row(r) for r in db.execute("SELECT * FROM tasks ORDER BY updated DESC")]


@app.post("/api/tasks", status_code=201)
def create_task(task: Task):
    id = uid()
    with connect() as db:
        db.execute("INSERT INTO tasks VALUES(?,?,?,?)", (id, 1, task.model_dump_json(), time.time()))
    return {"id": id}


@app.put("/api/tasks/{id}")
def edit_task(id: str, task: Task, revision: int):
    with connect() as db:
        get(db, "tasks", id)
        count = db.execute("UPDATE tasks SET spec=?,revision=revision+1,updated=? WHERE id=? AND revision=?", (
            task.model_dump_json(), time.time(), id, revision)).rowcount
        if not count:
            raise HTTPException(409, "Task wurde zwischenzeitlich geändert; neu laden")
    return {"id": id}


@app.delete("/api/tasks/{id}")
def delete_task(id: str):
    with connect() as db:
        get(db, "tasks", id)
        db.execute("DELETE FROM tasks WHERE id=?", (id,))
    return {"ok": True}


@app.post("/api/tasks/preview")
def preview(task: Task):
    return messages(task, Query(model="preview"), "Hier steht der zu klassifizierende Text.")


@app.get("/api/profiles")
def profiles():
    with connect() as db:
        return [spec_row(r) for r in db.execute("SELECT * FROM profiles")]


@app.post("/api/profiles", status_code=201)
def create_profile(profile: Profile):
    id = uid()
    with connect() as db:
        db.execute("INSERT INTO profiles VALUES(?,?)", (id, profile.model_dump_json()))
    return {"id": id}


@app.put("/api/profiles/{id}")
def update_profile(id: str, profile: Profile):
    with connect() as db:
        get(db, "profiles", id)
        db.execute("UPDATE profiles SET spec=? WHERE id=?", (profile.model_dump_json(), id))
    return {"id": id}


@app.get("/api/profiles/{id}/models")
def models(id: str):
    with connect() as db:
        profile = Profile.model_validate_json(get(db, "profiles", id)["spec"])
    try:
        return {"models": available_models(profile)}
    except Exception as exc:
        raise HTTPException(502, "Modellliste nicht verfügbar (" + type(exc).__name__ + "). URL und API-Key prüfen.") from exc


def dataset_row(row):
    result = dict(row)
    result.pop("path", None)
    result["columns"] = json.loads(result.pop("columns_json"))
    return result


@app.post("/api/datasets", status_code=201)
async def upload(request: Request, filename: str = "data.csv", delimiter: str = ",", encoding: Literal["utf-8-sig", "utf-8", "latin-1", "cp1252"] = "utf-8-sig"):
    if delimiter not in (",", ";", "\t", "|"):
        raise HTTPException(422, "Ungültiges Trennzeichen")
    limit = int(os.environ.get("TEXTLAB_MAX_UPLOAD_BYTES", 1024 ** 3))
    id = uid()
    path = root() / (id + ".csv")
    size = 0
    try:
        with path.open("wb") as output:
            async for chunk in request.stream():
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, "Upload überschreitet das konfigurierte Größenlimit")
                output.write(chunk)
        if not size:
            raise HTTPException(422, "Leere Datei")
        with connect() as db:
            db.execute("INSERT INTO datasets(id,name,path,bytes,delimiter,encoding,status,created) VALUES(?,?,?,?,?,?,?,?)", (
                id, Path(filename).name[:250], str(path), size, delimiter, encoding, "uploaded", time.time()))
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return {"id": id}


@app.get("/api/datasets")
def datasets():
    with connect() as db:
        return [dataset_row(r) for r in db.execute("SELECT * FROM datasets ORDER BY created DESC")]


@app.get("/api/datasets/{id}/preview")
def dataset_preview(id: str):
    with connect() as db:
        get(db, "datasets", id)
        return [json.loads(r[0]) for r in db.execute("SELECT data FROM records WHERE dataset_id=? ORDER BY row_no LIMIT 10", (id,))]


@app.post("/api/jobs", status_code=201)
def create_job(job: NewJob):
    with connect() as db:
        task = get(db, "tasks", job.task_id)
        profile = get(db, "profiles", job.profile_id)
        dataset = get(db, "datasets", job.dataset_id)
        if dataset["status"] != "ready" or dataset["total"] == 0:
            raise HTTPException(409, "Datensatz muss vollständig importiert und nicht leer sein")
        if job.text_column not in json.loads(dataset["columns_json"]):
            raise HTTPException(422, "Unbekannte Textspalte")
        snapshot = snapshot_for(task, profile, job.query, job.text_column)
        id = enqueue(db, job.name, dataset, snapshot)
    return {"id": id}


def job_row(row, detail=False):
    result = dict(row)
    snapshot = json.loads(result.pop("snapshot"))
    result["model"] = snapshot["query"]["model"]
    result["task_name"] = snapshot["task"]["name"]
    if detail:
        result["snapshot"] = snapshot
    return result


@app.get("/api/jobs")
def jobs():
    with connect() as db:
        return [job_row(r) for r in db.execute("SELECT * FROM jobs ORDER BY created DESC LIMIT 500")]


@app.get("/api/jobs/{id}")
def job_detail(id: str):
    with connect() as db:
        result = job_row(get(db, "jobs", id), True)
        result["metrics"] = {k: result[k] for k in ("requests", "prompt_tokens", "completion_tokens")}
        result["metrics"]["avg_seconds"] = result["total_seconds"] / max(result["done"], 1)
    return result


@app.post("/api/jobs/{id}/{action}")
def control(id: str, action: Literal["pause", "resume", "cancel"]):
    transitions = {"pause": ({"queued", "running"}, "pausing"), "resume": ({"paused"}, "queued"), "cancel": ({"queued", "running", "paused", "pausing"}, "cancelling")}
    allowed, target = transitions[action]
    with connect() as db:
        # Immediate transaction prevents stale read-modify-write against worker completion.
        db.execute("BEGIN IMMEDIATE")
        job = get(db, "jobs", id)
        if job["status"] not in allowed:
            raise HTTPException(409, "Aktion für diesen Jobstatus nicht verfügbar")
        db.execute("UPDATE jobs SET status=?,updated=? WHERE id=?", (target, time.time(), id))
    return {"status": target}


@app.get("/api/jobs/{id}/results")
def results(id: str, after: int = 0, limit: int = 50):
    limit = min(max(limit, 1), 200)
    with connect() as db:
        job = get(db, "jobs", id)
        rows = db.execute("SELECT r.*,d.data FROM results r JOIN records d ON d.dataset_id=? AND d.row_no=r.row_no WHERE r.job_id=? AND r.row_no>? ORDER BY r.row_no LIMIT ?", (
            job["dataset_id"], id, after, limit)).fetchall()
    return [result_row(r) for r in rows]


def result_row(row):
    row = dict(row)
    row["labels"] = json.loads(row["labels"])
    for field in ("evidence", "attempt_outputs"):
        row[field] = json.loads(row[field])
    row["source"] = json.loads(row.pop("data"))
    return row


def export_rows(id, dataset_id):
    # Short keyset pages: no hour-long SQLite read transaction pinning the WAL.
    after = 0
    while True:
        with connect() as db:
            rows = db.execute("SELECT r.*,d.data FROM results r JOIN records d ON d.dataset_id=? AND d.row_no=r.row_no WHERE r.job_id=? AND r.row_no>? ORDER BY r.row_no LIMIT 1000", (dataset_id, id, after)).fetchall()
        if not rows:
            break
        for row in rows:
            yield result_row(row)
        after = rows[-1]["row_no"]


def safe_cell(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


EXPORT_FIELDS = ["row_no", "labels", "rationale", "status", "error", "raw", "attempts", "seconds", "prompt_tokens", "completion_tokens", "evidence", "thinking", "attempt_outputs"]


@app.get("/api/jobs/{id}/export")
def export(id: str, format: Literal["csv", "jsonl", "parquet"] = "csv"):
    with connect() as db:
        job = get(db, "jobs", id)
        dataset = get(db, "datasets", job["dataset_id"])
    if job["status"] not in ("completed", "completed_with_errors", "cancelled"):
        raise HTTPException(409, "Für einen konsistenten Export Job abschließen oder abbrechen")
    headers = {"Content-Disposition": f'attachment; filename="textlab-{id}.{format}"'}
    if format == "jsonl":
        def json_chunks():
            batch = []
            for row in export_rows(id, job["dataset_id"]):
                batch.append(dumps(row) + "\n")
                if len(batch) == 1000:
                    yield "".join(batch)
                    batch.clear()
            if batch:
                yield "".join(batch)
        return StreamingResponse(json_chunks(), media_type="application/x-ndjson", headers=headers)
    columns = json.loads(dataset["columns_json"])

    def flat_rows():
        for row in export_rows(id, job["dataset_id"]):
            flat = {"source." + key: row["source"].get(key, "") for key in columns}
            flat.update({"classification." + key: dumps(row[key]) if key in ("labels", "evidence", "attempt_outputs") else row[key] for key in EXPORT_FIELDS})
            yield flat

    fields = ["source." + c for c in columns] + ["classification." + c for c in EXPORT_FIELDS]
    if format == "csv":
        def generate():
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=fields)
            yield "\ufeff"
            writer.writeheader()
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)
            for index, row in enumerate(flat_rows(), 1):
                writer.writerow({k: safe_cell(v) for k, v in row.items()})
                if index % 1000 == 0:
                    yield output.getvalue()
                    output.seek(0)
                    output.truncate(0)
            if output.tell():
                yield output.getvalue()
        return StreamingResponse(generate(), media_type="text/csv; charset=utf-8", headers=headers)
    import pyarrow as pa
    import pyarrow.parquet as pq
    fd, path = tempfile.mkstemp(suffix=".parquet", dir=root())
    os.close(fd)
    # Explicit schema also handles empty and all-null first row groups.
    schema = pa.schema([(key, pa.int64() if key.split(".")[-1] in ("row_no", "attempts", "prompt_tokens", "completion_tokens") and key.startswith("classification.") else pa.float64() if key == "classification.seconds" else pa.string()) for key in fields])
    try:
        with pq.ParquetWriter(path, schema, compression="zstd") as writer:
            batch = []
            for row in flat_rows():
                batch.append(row)
                if len(batch) == 1000:
                    writer.write_table(pa.Table.from_pylist(batch, schema=schema))
                    batch.clear()
            if batch:
                writer.write_table(pa.Table.from_pylist(batch, schema=schema))
    except BaseException:
        Path(path).unlink(missing_ok=True)
        raise
    return FileResponse(path, filename=f"textlab-{id}.parquet", background=BackgroundTask(Path(path).unlink, missing_ok=True))


from .eval_api import router as evaluation_router
app.include_router(evaluation_router)

app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="frontend")
