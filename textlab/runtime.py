import time
from .db import connect


def timed_batch(job, fn):
    start = time.monotonic()
    with connect() as db:
        changed=db.execute("UPDATE jobs SET started_at=COALESCE(started_at,?),active_since=? WHERE id=? AND status='running'",(time.time(),time.time(),job['id'])).rowcount
    if not changed:
        return
    try:
        return fn(job)
    finally:
        with connect() as db:
            db.execute('UPDATE jobs SET active_seconds=active_seconds+?,active_since=NULL WHERE id=?',(time.monotonic()-start,job['id']))


def runtime_metrics(job):
    complete=bool(job.get('runtime_complete',0))
    active=job.get('active_seconds') if complete else None
    if active is not None and job.get('active_since'):
        active+=max(0,time.time()-job['active_since'])
    elapsed=(job.get('finished_at') or time.time())-job['started_at'] if complete and job.get('started_at') else None
    done=job.get('done',0)
    return {'timing_complete':complete,'started_at':job.get('started_at'),'finished_at':job.get('finished_at'),
            'active_seconds':active,'elapsed_seconds':elapsed,
            'documents_per_second':done/active if active and done else None,
            'successful_documents_per_second':(done-job.get('failed',0))/active if active and done else None,
            'mean_document_seconds':job['total_seconds']/done if done else None,
            'completion_tokens_per_second':job.get('completion_tokens',0)/active if active and done else None}
