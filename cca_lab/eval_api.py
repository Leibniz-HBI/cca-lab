import json
import os
import time
from collections import Counter
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse, FileResponse, JSONResponse
from starlette.background import BackgroundTask
from pathlib import Path

from .db import connect, dumps, uid
from .evaluation import gold_labels, TERMINAL
from .jobs import snapshot_for, enqueue
from .models import GoldSet, NewEvaluation, Task, validate_labels

router = APIRouter(prefix='/api', tags=['Evaluation'])


def fetch(db, table, id):
    row = db.execute(f'SELECT * FROM {table} WHERE id=?',(id,)).fetchone()
    if row is None:
        raise HTTPException(404,'Not found')
    return dict(row)


def gold_row(row):
    row = dict(row)
    for key in ('spec','label_counts'):
        row[key] = json.loads(row[key])
    return row


@router.get('/gold-sets')
def gold_sets():
    with connect() as db:
        return [gold_row(r) for r in db.execute('SELECT * FROM gold_sets ORDER BY created DESC')]


@router.post('/gold-sets',status_code=201)
def register_gold(spec: GoldSet):
    return save_gold(spec)


@router.put('/gold-sets/{id}')
def edit_gold(id: str, spec: GoldSet):
    return save_gold(spec, id)


def save_gold(spec: GoldSet, edit_id=None):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        dataset = fetch(db,'datasets',spec.dataset_id)
        if dataset['status'] != 'ready' or dataset['total'] == 0:
            raise HTTPException(409,'Dataset must be fully imported and nonempty')
        limit = int(os.environ.get('CCA_LAB_MAX_EVAL_ROWS','50000'))
        if dataset['total'] > limit:
            raise HTTPException(422,f'Evaluation datasets are limited to {limit} rows')
        if not {spec.doc_id_column,spec.text_column,spec.gold_column}.issubset(json.loads(dataset['columns_json'])):
            raise HTTPException(422,'Column mapping contains unknown columns')
        existing = fetch(db, 'gold_sets', edit_id) if edit_id else None
        used = existing and db.execute('SELECT 1 FROM evaluations WHERE gold_id=? LIMIT 1', (edit_id,)).fetchone()
        if spec.context_column and spec.context_column not in json.loads(dataset["columns_json"]):
            raise HTTPException(422,"Unknown context column")
        id = uid() if not existing or used else edit_id
        if existing and not used:
            db.execute('DELETE FROM gold_rows WHERE gold_id=?', (id,))
            db.execute('UPDATE gold_sets SET dataset_id=?,spec=?,total=? WHERE id=?', (spec.dataset_id,spec.model_dump_json(),dataset['total'],id))
        else:
            db.execute('INSERT INTO gold_sets(id,dataset_id,spec,total,label_counts,created) VALUES(?,?,?,?,?,?)',(id,spec.dataset_id,spec.model_dump_json(),dataset['total'],'{}',time.time()))
        seen, counts = set(), Counter()
        for row in db.execute('SELECT row_no,data FROM records WHERE dataset_id=? ORDER BY row_no',(spec.dataset_id,)):
            data = json.loads(row['data'])
            doc_id = data[spec.doc_id_column].strip()
            if not doc_id or doc_id in seen:
                raise HTTPException(422,f"Row {row['row_no']}: doc_id is empty or duplicated")
            if not data[spec.text_column].strip():
                raise HTTPException(422,f"Row {row['row_no']}: text is empty")
            seen.add(doc_id)
            try:
                labels = gold_labels(data[spec.gold_column],spec)
            except ValueError as exc:
                raise HTTPException(422,f"Row {row['row_no']}: {exc}") from exc
            counts.update(labels)
            db.execute('INSERT INTO gold_rows VALUES(?,?,?,?)',(id,row['row_no'],doc_id,dumps(labels)))
        db.execute('UPDATE gold_sets SET label_counts=? WHERE id=?',(dumps(dict(counts)),id))
    return {'id':id, 'revised_from':edit_id if used else None}


@router.get('/gold-sets/{id}/preview')
def gold_preview(id: str):
    with connect() as db:
        gold = fetch(db,'gold_sets',id)
        spec = json.loads(gold['spec'])
        rows = db.execute('SELECT g.*,r.data FROM gold_rows g JOIN records r ON r.dataset_id=? AND r.row_no=g.row_no WHERE g.gold_id=? ORDER BY g.row_no LIMIT 10',(gold['dataset_id'],id)).fetchall()
    return [{'doc_id':r['doc_id'],'row_no':r['row_no'],'text':json.loads(r['data'])[spec['text_column']],'gold_labels':json.loads(r['labels'])} for r in rows]


@router.post('/evaluations',status_code=201)
def create_evaluation(spec: NewEvaluation):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        gold = fetch(db,'gold_sets',spec.gold_id)
        mapping = json.loads(gold['spec'])
        task_row = fetch(db,'tasks',spec.task_id)
        task = Task.model_validate_json(task_row['spec'])
        if mapping['mode'] != task.mode:
            raise HTTPException(422,'Gold dataset and task must use the same label mode')
        # Verify every gold assignment, including empty label sets, before enqueuing any request.
        for row in db.execute('SELECT row_no,labels FROM gold_rows WHERE gold_id=?',(spec.gold_id,)):
            try:
                validate_labels(json.loads(row['labels']),task)
            except ValueError as exc:
                raise HTTPException(422,f"Gold-Row {row['row_no']} does not match task: {exc}") from exc
        dataset = fetch(db,'datasets',gold['dataset_id'])
        profiles = {v.profile_id:fetch(db,'profiles',v.profile_id) for v in spec.variants}
        id, now = uid(),time.time()
        db.execute('INSERT INTO evaluations(id,name,gold_id,task_snapshot,created) VALUES(?,?,?,?,?)',(id,spec.name,spec.gold_id,dumps({'task':{'codebook':task.codebook},'task_id':task_row['id'],'task_revision':task_row['revision']}),now))
        jobs = []
        ordinal = 0
        for variant in spec.variants:
            seeds = variant.seeds or spec.seeds or [variant.query.seed]
            for seed in seeds:
                query = variant.query.model_copy(update={'seed': seed})
                try:
                    snapshot = snapshot_for(task_row,profiles[variant.profile_id],query,mapping['text_column'],mapping.get('context_column'))
                except ValueError as exc:
                    raise HTTPException(422,str(exc)) from exc
                run_name = variant.name + (f' · seed={seed}' if len(seeds)>1 else '')
                snapshot.update(evaluation_id=id,gold_id=spec.gold_id,variant=run_name,experiment_name=variant.name)
                job_id = enqueue(db,f'{spec.name} / {run_name}',dataset,snapshot,now+ordinal*.000001)
                db.execute('INSERT INTO evaluation_runs VALUES(?,?,?,?)',(id,job_id,run_name,ordinal))
                jobs.append(job_id); ordinal += 1
    return {'id':id,'job_ids':jobs}


def evaluation_info(db, row, detail=False):
    row = dict(row)
    row.pop('report_json',None)
    row['task_snapshot'] = json.loads(row['task_snapshot'])
    runs = [dict(r) for r in db.execute('SELECT j.*,r.name AS variant_name FROM evaluation_runs r JOIN jobs j ON j.id=r.job_id WHERE r.evaluation_id=? ORDER BY r.ordinal',(row['id'],))]
    for run in runs:
        from .runtime import runtime_metrics
        run['runtime']=runtime_metrics(run)
        run['name']=run.pop('variant_name')
        snapshot = json.loads(run.pop('snapshot'))
        run['model'] = snapshot['query']['model']
        run['connection'] = {k:snapshot['profile'][k] for k in ('name','provider','base_url')}
        run['query'] = snapshot['query']
        if detail:
            run['snapshot'] = snapshot
    statuses = [r['status'] for r in runs]
    ready = db.execute('SELECT report_json IS NOT NULL FROM evaluations WHERE id=?',(row['id'],)).fetchone()[0]
    if row['report_error']:
        status = 'report_failed'
    elif statuses and all(s in TERMINAL for s in statuses):
        status = ('cancelled' if all(s=='cancelled' for s in statuses) else 'completed_with_errors' if any(s!='completed' for s in statuses) else 'completed') if ready else 'evaluating'
    elif 'running' in statuses:
        status = 'running'
    elif 'cancelling' in statuses:
        status = 'cancelling'
    elif 'pausing' in statuses:
        status = 'pausing'
    elif 'queued' in statuses:
        status = 'queued'
    else:
        status = 'paused'
    row.update(status=status,report_ready=bool(ready),runs=runs,total=sum(r['total'] for r in runs),done=sum(r['done'] for r in runs),failed=sum(r['failed'] for r in runs))
    from .jobs import request_counts
    counts=[request_counts(r['total'],{'query':r['query'],'task':row['task_snapshot']['task']}) for r in runs]
    row['query_count']={k:sum(c[k] for c in counts) for k in ('planned','maximum_attempts','decisions','documents','runs')}
    return row


@router.get('/evaluations')
def evaluations():
    with connect() as db:
        return [evaluation_info(db,r) for r in db.execute('SELECT id,name,gold_id,task_snapshot,created,report_error FROM evaluations ORDER BY created DESC LIMIT 500')]


@router.get('/evaluations/{id}')
def evaluation_detail(id: str):
    with connect() as db:
        return evaluation_info(db,fetch(db,'evaluations',id),True)


@router.post('/evaluations/{id}/{action}')
def evaluation_control(id: str,action: Literal['pause','resume','cancel','retry-report']):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        evaluation = fetch(db,'evaluations',id)
        if action == 'retry-report':
            if not evaluation['report_error']:
                raise HTTPException(409,'No failed report to retry')
            db.execute('UPDATE evaluations SET report_error=NULL WHERE id=?',(id,))
            return {'ok':True}
        allowed,target = {'pause':(('queued','running'),'pausing'),'resume':(('paused',),'queued'),'cancel':(('queued','running','paused','pausing'),'cancelling')}[action]
        placeholders = ','.join('?' for _ in allowed)
        count = db.execute(f'UPDATE jobs SET status=?,updated=? WHERE id IN (SELECT job_id FROM evaluation_runs WHERE evaluation_id=?) AND status IN ({placeholders})',(target,time.time(),id,*allowed)).rowcount
        if not count:
            raise HTTPException(409,'No matching variant for this action')
    return {'updated_variants':count}


def ready_report(id):
    with connect() as db:
        evaluation = fetch(db,'evaluations',id)
    if not evaluation['report_json']:
        raise HTTPException(409,evaluation['report_error'] or 'The worker calculates the report after all variants finish')
    return json.loads(evaluation['report_json'])


@router.get('/evaluations/{id}/report')
def report(id: str,scope: Literal['valid','common']='common',format: Literal['json','csv','class_csv','html','zip']='json'):
    result = ready_report(id)
    from .reports import table_csv, html_report, report_zip
    headers = {'Content-Disposition':f'attachment; filename="evaluation-{id}-{scope}.{format if format!="class_csv" else "classes.csv"}"'}
    if format == 'json':
        return JSONResponse({**{k:v for k,v in result.items() if k!='scopes'},'scope':scope,'runs':result['scopes'][scope]['runs'],'groups':result['scopes'][scope].get('groups',[])},headers=headers)
    if format in ('csv','class_csv'):
        return Response(table_csv(result,scope,classes=format=='class_csv'),media_type='text/csv; charset=utf-8',headers=headers)
    if format == 'html':
        return Response(html_report(result,scope),media_type='text/html',headers=headers)
    path = report_zip(result,scope)
    return FileResponse(path,filename=f'evaluation-{id}-{scope}.zip',background=BackgroundTask(Path(path).unlink,missing_ok=True))


@router.get('/evaluations/{id}/chart')
def chart(id: str,scope: Literal['valid','common']='common',kind: Literal['overview','classes','confusion']='overview',metric: str='f1_macro',job_id: str|None=None,format: Literal['svg','png']='svg'):
    from .reports import render_chart
    try:
        content = render_chart(ready_report(id),scope,kind,metric,job_id,format)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    return Response(content,media_type='image/svg+xml' if format=='svg' else 'image/png',headers={'Content-Disposition':f'inline; filename="evaluation-{id}-{scope}-{kind}.{format}"'})


def prediction_rows(id, job_id=None, after=0, limit=None):
    with connect() as db:
        evaluation = fetch(db,'evaluations',id)
        gold = fetch(db,'gold_sets',evaluation['gold_id'])
        spec = json.loads(gold['spec'])
        runs = [dict(r) for r in db.execute('SELECT r.*,j.snapshot FROM evaluation_runs r JOIN jobs j ON j.id=r.job_id WHERE evaluation_id=? ORDER BY ordinal',(id,))]
    if job_id is not None:
        runs = [r for r in runs if r['job_id']==job_id]
        if not runs:
            raise HTTPException(404,'Variant does not belong to this evaluation')
    for run in runs:
        cursor,emitted = after,0
        while True:
            size = min(500,limit-emitted) if limit is not None else 500
            if size<=0:
                break
            with connect() as db:
                rows = db.execute('''SELECT g.row_no,g.doc_id,g.labels gold_labels,d.data,
                    r.self_reported_confidence,r.alternative_interpretations,r.candidate_interpretations,r.labels,r.rationale,r.evidence,r.thinking,r.attempt_outputs,r.status,r.error,r.raw,r.attempts,r.seconds
                    FROM gold_rows g JOIN records d ON d.dataset_id=? AND d.row_no=g.row_no
                    LEFT JOIN results r ON r.job_id=? AND r.row_no=g.row_no
                    WHERE g.gold_id=? AND g.row_no>? ORDER BY g.row_no LIMIT ?''',
                    (gold['dataset_id'],run['job_id'],gold['id'],cursor,size)).fetchall()
            if not rows:
                break
            for row in rows:
                result = dict(row)
                result['gold_labels'] = json.loads(result['gold_labels'])
                raw_labels = result.pop('labels')
                result['predicted_labels'] = json.loads(raw_labels) if result['status'] in ('ok','fallback') else None
                result['text'] = json.loads(result.pop('data'))[spec['text_column']]
                for field in ('evidence','attempt_outputs','alternative_interpretations','candidate_interpretations'):
                    result[field] = json.loads(result[field] or '[]')
                result['status'] = result['status'] or 'not_processed'
                result['exact_match'] = set(result['gold_labels']) == set(result['predicted_labels']) if result['predicted_labels'] is not None else False
                result.update(variant=run['name'],job_id=run['job_id'],seed=json.loads(run['snapshot'])['query'].get('seed'),fallback_used=result['status']=='fallback')
                from .executor import component_details
                with connect() as db:result['component_results']=component_details(db,run['job_id'],row['row_no'])
                yield result
            cursor = rows[-1]['row_no']
            emitted += len(rows)


@router.get('/evaluations/{id}/predictions')
def predictions(id: str,job_id: str,after: int=0,limit: int=50):
    return list(prediction_rows(id,job_id,after,min(max(limit,1),200)))


@router.get('/evaluations/{id}/export-predictions')
def export_predictions(id: str,format: Literal['csv','jsonl']='csv'):
    ready_report(id)
    from .reports import prediction_chunks
    return StreamingResponse(prediction_chunks(id,format),media_type='text/csv' if format=='csv' else 'application/x-ndjson',headers={'Content-Disposition':f'attachment; filename="evaluation-{id}-predictions.{format}"'})
