import json
import time

from .db import dumps, uid
from .models import Task, Profile


def resolved_task(task, query):
    obj = task.model_dump()
    for field in ("rationale", "evidence", "thinking"):
        if getattr(query, field) is not None:
            obj["execution_defaults"][field] = getattr(query, field)
    return Task.model_validate(obj)


def snapshot_for(task_row, profile_row, query, text_column):
    task = resolved_task(Task.model_validate_json(task_row["spec"]), query)
    from .thinking import thinking_body
    thinking_body(Profile.model_validate_json(profile_row["spec"]), task.thinking, query.extra_body)
    from .llm import PROMPT_PROTOCOL
    return {"prompt_protocol": PROMPT_PROTOCOL, "task": task.model_dump(), "task_id": task_row["id"], "task_revision": task_row["revision"],
            "profile": json.loads(profile_row["spec"]), "query": query.model_dump(), "text_column": text_column,
            "framework_version": "0.9.0"}


def enqueue(db, name, dataset, snapshot, created=None):
    id, now = uid(), time.time() if created is None else created
    db.execute("INSERT INTO jobs(id,name,dataset_id,snapshot,status,total,created,updated,runtime_complete) VALUES(?,?,?,?,?,?,?,?,1)", (
        id, name, dataset["id"], dumps(snapshot), "queued", dataset["total"], now, now))
    return id
