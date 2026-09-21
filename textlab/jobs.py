from . import __version__
import json
import time

from .db import dumps, uid
from .models import Task, Profile


def resolved_task(task, query):
    obj = task.model_dump()
    for field in ("rationale", "evidence", "alternatives", "confidence", "thinking", "default_label"):
        obj["execution_defaults"][field] = getattr(query, field)
    return Task.model_validate(obj)


def snapshot_for(task_row, profile_row, query, text_column, context_column=None):
    query=query.model_copy(update={"prompt_protocol":"experiment-v3"})
    task = resolved_task(Task.model_validate_json(task_row["spec"]), query)
    if query.strategy == "binary" and task.mode != "multi":
        raise ValueError("Binary decomposition requires a multi-label task")
    if query.use_context and not context_column:
        raise ValueError("Map a context column before enabling context")
    from .thinking import thinking_body
    thinking_body(Profile.model_validate_json(profile_row["spec"]), task.thinking, query.extra_body)
    return {"prompt_protocol": query.prompt_protocol, "task": {"codebook": task.codebook}, "task_id": task_row["id"], "task_revision": task_row["revision"],
            "profile": json.loads(profile_row["spec"]), "query": query.model_dump(), "text_column": text_column, "context_column": context_column,
            "framework_version": __version__}


def enqueue(db, name, dataset, snapshot, created=None):
    id, now = uid(), time.time() if created is None else created
    db.execute("INSERT INTO jobs(id,name,dataset_id,snapshot,status,total,created,updated,runtime_complete) VALUES(?,?,?,?,?,?,?,?,1)", (
        id, name, dataset["id"], dumps(snapshot), "queued", dataset["total"], now, now))
    return id


def request_counts(total, snapshot):
    import math
    q = snapshot['query']
    categories = len(snapshot['task']['codebook']['task']['categories']) if q.get('strategy') == 'binary' else 1
    planned = math.ceil(total / q.get('batch_size', 1)) * categories
    # Character-based splits can increase base requests up to one item/request.
    return {'planned': planned, 'decisions': total * categories,
            'maximum_attempts': total * categories * (q['retries'] + 1),
            'runs': 1, 'documents': total}


def validate_mapping(dataset, text_column, context_column):
    columns = json.loads(dataset['columns_json'])
    if text_column not in columns or (context_column and context_column not in columns):
        raise ValueError('Unknown text or context column')
    if context_column == text_column:
        raise ValueError('Context and text must use separate columns')


def snapshot_query(snapshot):
    from .models import Query
    values=dict(snapshot['query'])
    if snapshot.get('prompt_protocol','cca-reference-v2')=='cca-reference-v2':
        defaults=snapshot['task'].get('execution_defaults',{})
        for key in ('rationale','evidence','thinking','alternatives','confidence','default_label'):
            if values.get(key) is None:
                values[key]=defaults.get(key, 'default' if key=='thinking' else None if key=='default_label' else False)
    return Query.model_validate(values)
