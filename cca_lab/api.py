from . import __version__
import logging
import uuid
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


log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    from .logging_config import configure_logging
    configure_logging()
    init()
    log.info("api_started")
    yield
    log.info("api_stopped")


app = FastAPI(title="CCA-Lab", version=__version__, lifespan=lifespan)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = uuid.uuid4().hex[:16]
    request.state.request_id = request_id
    started = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("request_failed request_id=%s method=%s", request_id, request.method)
        raise
    route = request.scope.get("route")
    path = getattr(route, "path", "<static-or-unmatched>")
    level = logging.WARNING if response.status_code >= 400 else logging.DEBUG
    log.log(level, "request_completed request_id=%s method=%s route=%s status=%s seconds=%.3f",
            request_id, request.method, path, response.status_code, time.monotonic()-started)
    response.headers["X-Request-ID"] = request_id
    return response


def get(db, table, id):
    # table is always a hard-coded internal identifier.
    row = db.execute(f"SELECT * FROM {table} WHERE id=?", (id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Not found")
    return dict(row)


def spec_row(row):
    result = dict(row)
    result["spec"] = json.loads(result["spec"])
    return result


@app.get("/api/health")
def health():
    with connect() as db:
        row = db.execute("SELECT heartbeat FROM worker_state WHERE id=1").fetchone()
    return {"api": "ok", "version": __version__, "worker_online": bool(row and time.time() - row[0] < 15)}


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


@app.post("/api/tasks/import-cca", status_code=201)
async def import_cca(request: Request):
    from .cca import from_codebook
    from pydantic import ValidationError
    log.info("cca_import_started request_id=%s", request.state.request_id)
    content=bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content)>5*1024*1024:
            log.warning("cca_import_rejected request_id=%s reason=size_limit", request.state.request_id)
            raise HTTPException(413,"Maximum codebook size is 5 MiB")
    try:
        def unique_pairs(pairs):
            result={}
            for key,value in pairs:
                if key in result:raise ValueError('Duplicate JSON key: '+key)
                result[key]=value
            return result
        doc=json.loads(content.decode('utf-8-sig'),object_pairs_hook=unique_pairs)
        task=from_codebook(doc)
    except (ValueError,UnicodeError,ValidationError,RecursionError) as exc:
        log.warning("cca_import_rejected request_id=%s reason=validation error_type=%s bytes=%s", request.state.request_id, type(exc).__name__, len(content))
        raise HTTPException(422,'CCA import: '+str(exc)[:2000]) from exc
    result = create_task(task)
    log.info("cca_import_completed request_id=%s task_id=%s categories=%s bytes=%s", request.state.request_id, result["id"], len(task.categories), len(content))
    return result


@app.get("/api/tasks/{id}/export-cca")
def export_cca(id: str):
    from .cca import to_codebook
    from fastapi.responses import Response
    with connect() as db:row=get(db,'tasks',id)
    try:doc=to_codebook(Task.model_validate_json(row['spec']))
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    return Response(json.dumps(doc,ensure_ascii=False,indent=2,allow_nan=False),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="codebook-{id}.cca.json"'})


@app.put("/api/tasks/{id}")
def edit_task(id: str, task: Task, revision: int):
    with connect() as db:
        get(db, "tasks", id)
        count = db.execute("UPDATE tasks SET spec=?,revision=revision+1,updated=? WHERE id=? AND revision=?", (
            task.model_dump_json(), time.time(), id, revision)).rowcount
        if not count:
            raise HTTPException(409, "Task has changed; reload before saving")
    return {"id": id}


@app.delete("/api/tasks/{id}")
def delete_task(id: str):
    with connect() as db:
        get(db, "tasks", id)
        db.execute("DELETE FROM tasks WHERE id=?", (id,))
    return {"ok": True}


@app.post("/api/tasks/preview")
def preview(task: Task):
    return messages(task, Query(model="preview"), "The text to classify goes here.")


from pydantic import BaseModel, Field


class PreviewRequest(BaseModel):
    task: Task
    query: Query = Field(default_factory=lambda: Query(model="preview"))
    provider: Literal["openai", "ollama"] = "openai"
    text: str = "The text to classify goes here."
    context: str = ""
    samples: list[dict] | None = None
    category: str = ""


@app.post("/api/tasks/preview-request")
def preview_request(spec: PreviewRequest):
    from .jobs import resolved_task
    task = resolved_task(spec.task, spec.query)
    profile = Profile(name="Preview", provider=spec.provider)
    from .experiment import compile_request
    samples=spec.samples or [{"id":"1",**({"context":spec.context} if spec.query.use_context else {}),"text":spec.text}]
    try:path,body,_=compile_request(task,spec.query,profile,samples,spec.category)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    return {"prompt_protocol": spec.query.prompt_protocol, "path": path, "request": body,
            "note": "Illustrative request using the selected preview settings; no model is called."}


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
        raise HTTPException(502, "Model list unavailable (" + type(exc).__name__ + "). Check the URL and API key.") from exc


def dataset_row(row):
    result = dict(row)
    result["csv_available"] = Path(result.pop("path")).is_file()
    result["columns"] = json.loads(result.pop("columns_json"))
    return result


@app.post("/api/datasets", status_code=201)
async def upload(request: Request, filename: str = "data.csv", delimiter: str = ",", encoding: Literal["utf-8-sig", "utf-8", "latin-1", "cp1252"] = "utf-8-sig"):
    if delimiter not in (",", ";", "\t", "|"):
        raise HTTPException(422, "Invalid delimiter")
    limit = int(os.environ.get("CCA_LAB_MAX_UPLOAD_BYTES", 1024 ** 3))
    id = uid()
    path = root() / (id + ".csv")
    size = 0
    try:
        with path.open("wb") as output:
            async for chunk in request.stream():
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, "Upload exceeds the configured size limit")
                output.write(chunk)
        if not size:
            raise HTTPException(422, "Empty file")
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
            raise HTTPException(409, "Dataset must be fully imported and nonempty")
        if job.text_column not in json.loads(dataset["columns_json"]):
            raise HTTPException(422, "Unknown text column")
        try:
            from .jobs import validate_mapping
            validate_mapping(dataset,job.text_column,job.context_column)
            snapshot = snapshot_for(task, profile, job.query, job.text_column, job.context_column)
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from exc
        id = enqueue(db, job.name, dataset, snapshot)
    return {"id": id}


def job_row(row, detail=False):
    result = dict(row)
    snapshot = json.loads(result.pop("snapshot"))
    result["evaluation_id"] = snapshot.get("evaluation_id")
    result["prediction_id"] = snapshot.get("prediction_id")
    result["model"] = snapshot["query"]["model"]
    result["task_name"] = snapshot["task"]["codebook"]["title"]
    from .jobs import request_counts
    result["query_count"]=request_counts(result["total"],snapshot)
    if detail:
        with connect() as db:
            from .error_stats import error_statistics
            result["error_statistics"]=error_statistics(db,result["id"])
            result["component_progress"]={r[0]:r[1] for r in db.execute("SELECT status,COUNT(*) FROM components WHERE job_id=? GROUP BY status",(result["id"],))}
    if detail:
        result["snapshot"] = snapshot
    from .runtime import runtime_metrics
    result["runtime"] = runtime_metrics(result)
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
            raise HTTPException(409, "Action unavailable for this job status")
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



def error_rows(id, after=0, limit=None, include_recovered=True):
    with connect() as db:
        job=get(db,'jobs',id)
    emitted=0
    while True:
        size=min(200,limit-emitted) if limit is not None else 200
        if size<=0:return
        with connect() as db:
            rows=db.execute("SELECT r.*,d.data FROM results r JOIN records d ON d.dataset_id=? AND d.row_no=r.row_no WHERE r.job_id=? AND r.error_count>0 AND r.row_no>?" + ("" if include_recovered else " AND r.status!='ok'") + " ORDER BY r.row_no LIMIT ?",(job['dataset_id'],id,after,size)).fetchall()
        if not rows:return
        for row in rows:yield result_row(row)
        emitted+=len(rows);after=rows[-1]['row_no']


@app.get('/api/jobs/{id}/errors')
def job_errors(id: str, after: int=0, limit: int=50, include_recovered: bool=True, format: Literal['json','jsonl']='json'):
    with connect() as db:
        job=get(db,'jobs',id)
        count=db.execute("SELECT COUNT(*) FROM results WHERE job_id=? AND error_count>0" + ("" if include_recovered else " AND status!='ok'"),(id,)).fetchone()[0]
    if format=='jsonl':
        return StreamingResponse((dumps(r)+'\n' for r in error_rows(id,after,include_recovered=include_recovered)),media_type='application/x-ndjson',headers={'Content-Disposition':f'attachment; filename="job-{id}-errors.jsonl"'})
    rows=list(error_rows(id,after,min(max(limit,1),200),include_recovered))
    return {'rows':rows,'total':count,'next_after':rows[-1]['row_no'] if rows else after,'last_error':job['last_error'], 'status':job['status']}


def result_row(row):
    row = dict(row)
    row["fallback_used"] = row["status"] == "fallback"
    row["labels"] = json.loads(row["labels"])
    for field in ("evidence", "attempt_outputs", "alternative_interpretations", "candidate_interpretations"):
        row[field] = json.loads(row[field])
    from .executor import component_details
    with connect() as db:row["component_results"]=component_details(db,row["job_id"],row["row_no"])
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


EXPORT_FIELDS = ["component_results", "self_reported_confidence", "alternative_interpretations", "candidate_interpretations", "fallback_used", "error_count", "row_no", "labels", "rationale", "status", "error", "raw", "attempts", "seconds", "prompt_tokens", "completion_tokens", "evidence", "thinking", "attempt_outputs"]


@app.get("/api/jobs/{id}/export")
def export(id: str, format: Literal["csv", "jsonl", "parquet"] = "csv"):
    with connect() as db:
        job = get(db, "jobs", id)
        dataset = get(db, "datasets", job["dataset_id"])
    if job["status"] not in ("completed", "completed_with_errors", "cancelled"):
        raise HTTPException(409, "Complete or cancel the job before exporting")
    headers = {"Content-Disposition": f'attachment; filename="cca_lab-{id}.{format}"'}
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
            flat.update({"classification." + key: dumps(row[key]) if isinstance(row[key],(dict,list)) else row[key] for key in EXPORT_FIELDS})
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
    schema = pa.schema([(key, pa.bool_() if key == "classification.fallback_used" else pa.int64() if key.split(".")[-1] in ("error_count", "row_no", "attempts", "prompt_tokens", "completion_tokens") and key.startswith("classification.") else pa.float64() if key in ("classification.seconds", "classification.self_reported_confidence") else pa.string()) for key in fields])
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
    return FileResponse(path, filename=f"cca_lab-{id}.parquet", background=BackgroundTask(Path(path).unlink, missing_ok=True))


from .eval_api import router as evaluation_router
app.include_router(evaluation_router)
from .prediction import router as prediction_router
from .removal import router as removal_router
app.include_router(prediction_router)
app.include_router(removal_router)

from .uncertainty import router as uncertainty_router
app.include_router(uncertainty_router)




@app.get('/api/jobs/{id}/requests')
def request_log(id: str, after: int = 0, limit: int = 50):
    with connect() as db:
        get(db,'jobs',id)
        rows=db.execute('SELECT * FROM llm_requests WHERE job_id=? ORDER BY created,id LIMIT ? OFFSET ?', (id,min(max(limit,1),200),max(after,0))).fetchall()
    return [{**dict(r),'inputs':json.loads(r['inputs']),'request_json':json.loads(r['request_json']),'output_json':json.loads(r['output_json']) if r['output_json'] else None} for r in rows]


class ExperimentPreview(BaseModel):
    task_id: str
    dataset_id: str
    profile_id: str
    query: Query
    text_column: str
    context_column: str | None = None
    category: str = ''
    after: int = 0
    source_evaluation_job_id: str | None = None


@app.post('/api/experiments/preview')
def experiment_preview(spec: ExperimentPreview):
    from .experiment import prepare_item,compile_request,batches
    from .jobs import validate_mapping
    with connect() as db:
        dataset=get(db,'datasets',spec.dataset_id)
        if spec.source_evaluation_job_id:
            source=get(db,'jobs',spec.source_evaluation_job_id);saved=json.loads(source['snapshot'])
            if not saved.get('evaluation_id') or source['status'] not in ('completed','completed_with_errors'):raise HTTPException(422,'Expected completed evaluation run')
            task={'id':saved['task_id'],'revision':saved['task_revision'],'spec':dumps(saved['task'])};profile={'spec':dumps(saved['profile'])}
            spec.query=Query.model_validate(saved['query']).model_copy(update={'prompt_protocol':'experiment-v3'})
        else:
            task=get(db,'tasks',spec.task_id);profile=get(db,'profiles',spec.profile_id)
        try:
            validate_mapping(dataset,spec.text_column,spec.context_column)
            snapshot=snapshot_for(task,profile,spec.query,spec.text_column,spec.context_column)
            rows=db.execute('SELECT row_no,data FROM records WHERE dataset_id=? AND row_no>? ORDER BY row_no LIMIT ?', (spec.dataset_id,max(0,spec.after),spec.query.batch_size)).fetchall()
            items=[prepare_item(r['row_no'],json.loads(r['data']),snapshot) for r in rows]
            if not items:raise ValueError('No sample rows available')
            items=next(batches(items,spec.query))
            path,body,_=compile_request(Task(**snapshot['task']),spec.query,Profile.model_validate_json(profile['spec']),items,spec.category)
        except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    return {'prompt_protocol':'experiment-v3','path':path,'request':body,'note':'Exact request structure using selected dataset rows. No LLM request is sent.'}


@app.get('/api/jobs/{id}/requests.jsonl')
def export_requests(id: str):
    from .executor import request_chunks
    with connect() as db:get(db,'jobs',id)
    return StreamingResponse(request_chunks([id]),media_type='application/x-ndjson',headers={'Content-Disposition':f'attachment; filename="requests-{id}.jsonl"'})

app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="frontend")
