from . import __version__
"""Multi-task prediction batches with durable, streamed filesystem exports."""
import csv
import io
import json
import logging
import os
import shutil
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .db import connect, dumps, root, uid
from .models import NewPrediction, Variant, Query
from .jobs import enqueue, snapshot_for
from .runtime import runtime_metrics
from .evaluation import TERMINAL
from .eval_api import fetch

router=APIRouter(prefix='/api/predictions',tags=['Prediction'])
FORMATS={'csv','json','jsonl','parquet','manifest','agreement_csv','agreement_jsonl','requests'}


@router.post('',status_code=201)
def create_prediction(spec: NewPrediction):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        dataset=fetch(db,'datasets',spec.dataset_id)
        if dataset['status']!='ready' or not dataset['total']:
            raise HTTPException(409,'Dataset must be fully imported and nonempty')
        if spec.text_column not in json.loads(dataset['columns_json']):
            raise HTTPException(422,'Unknown text column')
        from .jobs import validate_mapping
        try:validate_mapping(dataset,spec.text_column,spec.context_column)
        except ValueError as exc:raise HTTPException(422,str(exc)) from exc
        source=None
        variants=spec.variants
        if spec.source_evaluation_job_id:
            source=fetch(db,'jobs',spec.source_evaluation_job_id)
            if not db.execute('SELECT 1 FROM evaluation_runs WHERE job_id=?',(source['id'],)).fetchone():raise HTTPException(422,'Source must belong to an evaluation')
            if source['status'] not in ('completed','completed_with_errors'):raise HTTPException(409,'Reuse requires a completed evaluation run')
            saved=json.loads(source['snapshot'])
            if spec.task_ids != [saved['task_id']]:raise HTTPException(422,'Reuse requires the evaluated task')
            tasks=[{'id':saved['task_id'],'revision':saved['task_revision'],'spec':dumps(saved['task'])}]
            variants=[Variant(name=saved.get('experiment_name','Evaluated configuration'),profile_id='snapshot',query=Query.model_validate(saved['query']))]
        else:tasks=[fetch(db,'tasks',tid) for tid in spec.task_ids]
        if len(tasks)*sum(len(v.seeds or spec.seeds or [v.query.seed]) for v in variants)>500:
            raise HTTPException(422,'Maximum 500 total prediction runs')
        id,now=uid(),time.time()
        db.execute('INSERT INTO predictions(id,name,dataset_id,created) VALUES(?,?,?,?)',(id,spec.name,spec.dataset_id,now))
        jobs=[];index=0
        for task in tasks:
            for variant in variants:
                profile={'spec':dumps(saved['profile'])} if source else fetch(db,'profiles',variant.profile_id)
                for seed in (variant.seeds or spec.seeds or [variant.query.seed]):
                    query=variant.query.model_copy(update={'seed':seed})
                    try:snapshot=snapshot_for(task,profile,query,spec.text_column,spec.context_column)
                    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
                    snapshot['prediction_id']=id
                    if source:
                        snapshot['source_evaluation_job_id']=source['id']
                        snapshot['source_evaluation_id']=saved['evaluation_id']
                    name=snapshot['task']['codebook']['title']
                    snapshot['experiment_name']=name+' / '+variant.name
                    job=enqueue(db,f'{spec.name} / {name} / {variant.name} · seed={seed}',dataset,snapshot,now+index*.000001)
                    db.execute('INSERT INTO prediction_runs VALUES(?,?,?,?)',(id,job,name,index));jobs.append(job);index+=1
    return {'id':id,'job_ids':jobs}


def info(db,prediction):
    p=dict(prediction)
    runs=[dict(r) for r in db.execute('SELECT j.*,r.task_name FROM prediction_runs r JOIN jobs j ON j.id=r.job_id WHERE r.prediction_id=? ORDER BY r.ordinal',(p['id'],))]
    for r in runs:
        r['snapshot']=json.loads(r['snapshot']);r['runtime']=runtime_metrics(r)
    states=[r['status'] for r in runs]
    if p['artifact_status']=='failed':status='export_failed'
    elif states and all(s in TERMINAL for s in states):
        status=('cancelled' if all(s=='cancelled' for s in states) else 'completed_with_errors' if any(s!='completed' for s in states) else 'completed') if p['artifact_status']=='ready' else 'exporting'
    else:
        status=next((s for s in ('running','cancelling','pausing','queued','paused') if s in states),'queued')
    from .repetitions import aggregate_runs
    p.update(groups=aggregate_runs(runs),runs=runs,status=status,total=sum(r['total'] for r in runs),done=sum(r['done'] for r in runs),failed=sum(r['failed'] for r in runs),artifacts=[dict(r) for r in db.execute('SELECT format,bytes FROM prediction_artifacts WHERE prediction_id=? ORDER BY format',(p['id'],))])
    from .jobs import request_counts
    counts=[request_counts(r['total'],r['snapshot']) for r in runs]
    p['query_count']={k:sum(c[k] for c in counts) for k in ('planned','maximum_attempts','decisions','documents','runs')}
    return p


@router.get('')
def list_predictions():
    with connect() as db:
        return [info(db,p) for p in db.execute('SELECT * FROM predictions ORDER BY created DESC LIMIT 500')]


@router.get('/{id}')
def detail(id: str):
    with connect() as db:return info(db,fetch(db,'predictions',id))


@router.post('/{id}/{action}')
def control(id: str,action: str):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE');p=fetch(db,'predictions',id)
        if action=='retry-export':
            if p['artifact_status']!='failed':raise HTTPException(409,'No failed export to retry')
            db.execute("UPDATE predictions SET artifact_status='pending',artifact_error=NULL WHERE id=?",(id,));return {'ok':True}
        if action not in ('pause','resume','cancel'):raise HTTPException(422,'Unknown action')
        allowed,target={'pause':(('queued','running'),'pausing'),'resume':(('paused',),'queued'),'cancel':(('queued','running','paused','pausing'),'cancelling')}[action]
        count=db.execute(f"UPDATE jobs SET status=?,updated=? WHERE id IN (SELECT job_id FROM prediction_runs WHERE prediction_id=?) AND status IN ({','.join('?' for _ in allowed)})",(target,time.time(),id,*allowed)).rowcount
        if not count:raise HTTPException(409,'No matching jobs for this action')
    return {'updated_jobs':count}


@router.get('/{id}/download/{format}')
def download(id: str,format: str):
    if format not in FORMATS:raise HTTPException(422,'Unsupported format')
    with connect() as db:
        p=fetch(db,'predictions',id)
        if p['artifact_status']!='ready':raise HTTPException(409,'Exports are not ready')
        row=db.execute('SELECT path FROM prediction_artifacts WHERE prediction_id=? AND format=?',(id,format)).fetchone()
    if not row or not Path(row['path']).is_file():raise HTTPException(404,'Stored export is missing from disk')
    return FileResponse(row['path'],filename=f'prediction-{id}.{"requests.jsonl" if format=="requests" else format.replace('_','.') if format!="manifest" else "manifest.json"}')


def prediction_rows(prediction):
    with connect() as db:
        runs=[dict(r) for r in db.execute('SELECT j.*,p.task_name FROM prediction_runs p JOIN jobs j ON j.id=p.job_id WHERE p.prediction_id=? ORDER BY p.ordinal',(prediction['id'],))]
    for run in runs:
        snapshot=json.loads(run['snapshot']);after=0
        while True:
            with connect() as db:
                rows=db.execute('''SELECT d.row_no,d.data,r.self_reported_confidence,r.alternative_interpretations,r.candidate_interpretations,r.labels,r.rationale,r.evidence,r.thinking,r.attempt_outputs,r.status,r.error,r.raw,r.attempts,r.seconds,r.prompt_tokens,r.completion_tokens
                FROM records d LEFT JOIN results r ON r.job_id=? AND r.row_no=d.row_no
                WHERE d.dataset_id=? AND d.row_no>? ORDER BY d.row_no LIMIT 500''',(run['id'],prediction['dataset_id'],after)).fetchall()
            if not rows:break
            for row in rows:
                out=dict(row);out['source']=json.loads(out.pop('data'))
                out['labels']=json.loads(out['labels']) if out['status'] in ('ok','fallback') else None
                out['candidate_interpretations']=json.loads(out['candidate_interpretations'] or '[]');out['alternative_interpretations']=json.loads(out['alternative_interpretations'] or '[]');out['evidence']=json.loads(out['evidence'] or '[]');out['attempt_outputs']=json.loads(out['attempt_outputs'] or '[]')
                out.update(seed=snapshot['query'].get('seed'),fallback_used=out['status']=='fallback',status=out['status'] or 'not_processed',task_id=snapshot['task_id'],task_name=run['task_name'],job_id=run['id'])
                from .executor import component_details
                with connect() as db:out['component_results']=component_details(db,run['id'],row['row_no'])
                out['configuration']=snapshot['query']
                yield out
            after=rows[-1]['row_no']


def build_artifacts(prediction):
    import pyarrow as pa
    import pyarrow.parquet as pq
    from .reports import safe_cell
    from contextlib import ExitStack
    base=root()/'predictions';base.mkdir(exist_ok=True)
    staging=base/('.building-'+prediction['id']);final=base/prediction['id']
    if staging.exists():shutil.rmtree(staging)
    staging.mkdir()
    with connect() as db:
        dataset=fetch(db,'datasets',prediction['dataset_id'])
        manifest=info(db,prediction)
    columns=json.loads(dataset['columns_json'])
    meta=['component_results','configuration','self_reported_confidence','alternative_interpretations','candidate_interpretations','seed','fallback_used','job_id','task_id','task_name','row_no','labels','rationale','evidence','thinking','attempt_outputs','status','error','raw','attempts','seconds','prompt_tokens','completion_tokens']
    fields=['source.'+c for c in columns]+['prediction.'+c for c in meta]
    integer={'seed','row_no','attempts','prompt_tokens','completion_tokens'}
    schema=pa.schema([(f,pa.bool_() if f=='prediction.fallback_used' else pa.int64() if f.startswith('prediction.') and f[11:] in integer else pa.float64() if f in ('prediction.seconds','prediction.self_reported_confidence') else pa.string()) for f in fields])
    with ExitStack() as stack:
        csvfile=stack.enter_context((staging/'results.csv').open('w',encoding='utf-8-sig',newline=''))
        jsonfile=stack.enter_context((staging/'results.json').open('w',encoding='utf-8'))
        jsonl=stack.enter_context((staging/'results.jsonl').open('w',encoding='utf-8'))
        parquet=stack.enter_context(pq.ParquetWriter(staging/'results.parquet',schema,compression='zstd'))
        writer=csv.DictWriter(csvfile,fieldnames=fields);writer.writeheader();jsonfile.write('[')
        first=True;batch=[]
        for row in prediction_rows(prediction):
            serialized=dumps(row);jsonfile.write(('' if first else ',\n')+serialized);first=False;jsonl.write(serialized+'\n')
            flat={'source.'+k:row['source'].get(k,'') for k in columns}
            flat.update({'prediction.'+k:dumps(row[k]) if isinstance(row[k],(dict,list)) else row[k] for k in meta})
            writer.writerow({k:safe_cell(v) for k,v in flat.items()});batch.append(flat)
            if len(batch)==500:parquet.write_table(pa.Table.from_pylist(batch,schema=schema));batch.clear()
        if batch:parquet.write_table(pa.Table.from_pylist(batch,schema=schema))
        jsonfile.write(']\n')
    from .uncertainty import agreement_rows, experiment_runs
    with (staging/'agreement.csv').open('w',encoding='utf-8',newline='') as csvout, (staging/'agreement.jsonl').open('w',encoding='utf-8') as jsonout:
        writer=None
        for row in agreement_rows(experiment_runs('predictions',prediction['id'])):
            if writer is None:
                writer=csv.DictWriter(csvout,fieldnames=list(row));writer.writeheader()
            writer.writerow({k:safe_cell(dumps(v) if isinstance(v,(list,dict)) else v) for k,v in row.items()})
            jsonout.write(dumps(row)+'\n')
    from .executor import request_chunks
    with (staging/'requests.jsonl').open('w',encoding='utf-8') as output:
        for chunk in request_chunks([r['id'] for r in manifest['runs']]):output.write(chunk)
    manifest.update(status='cancelled' if all(r['status']=='cancelled' for r in manifest['runs']) else 'completed_with_errors' if any(r['status']!='completed' for r in manifest['runs']) else 'completed',artifact_status='ready',framework_version=__version__,layout='one row per source record and task',created_at=time.time())
    (staging/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    if final.exists():shutil.rmtree(final)
    os.replace(staging,final)
    with connect() as db:
        db.execute('DELETE FROM prediction_artifacts WHERE prediction_id=?',(prediction['id'],))
        for format in FORMATS:
            path=final/('requests.jsonl' if format=='requests' else 'manifest.json' if format=='manifest' else 'agreement.'+format.split('_')[1] if format.startswith('agreement_') else 'results.'+format)
            db.execute('INSERT INTO prediction_artifacts VALUES(?,?,?,?)',(prediction['id'],format,str(path),path.stat().st_size))
        db.execute("UPDATE predictions SET artifact_status='ready',artifact_error=NULL WHERE id=?",(prediction['id'],))


def finalize_prediction():
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        p=db.execute("""SELECT * FROM predictions p WHERE artifact_status='pending' AND EXISTS(SELECT 1 FROM prediction_runs r WHERE r.prediction_id=p.id)
        AND NOT EXISTS(SELECT 1 FROM prediction_runs r JOIN jobs j ON j.id=r.job_id WHERE r.prediction_id=p.id AND (j.status NOT IN ('completed','completed_with_errors','cancelled') OR j.active_since IS NOT NULL)) ORDER BY created LIMIT 1""").fetchone()
        if not p:return False
        db.execute("UPDATE predictions SET artifact_status='building' WHERE id=?",(p['id'],))
    try:
        logging.getLogger(__name__).info("prediction_export_started prediction_id=%s", p["id"])
        build_artifacts(dict(p))
        logging.getLogger(__name__).info("prediction_export_completed prediction_id=%s", p["id"])
    except Exception:
        logging.getLogger(__name__).exception('Prediction export failed')
        with connect() as db:db.execute("UPDATE predictions SET artifact_status='failed',artifact_error='Export failed; check worker log and available disk space.' WHERE id=?",(p['id'],))
    return True
