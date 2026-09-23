"""Durable request accounting, per-item retries and binary aggregation."""
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
import httpx
from .db import connect,dumps,uid
from .models import Task,Query,Profile
from .experiment import prepare_item,batches,compile_request,perform


log=logging.getLogger("cca_lab.executor")

def request_once(job, snapshot, category, items, client):
    q=Query(**snapshot['query']);task=Task(**snapshot['task']);profile=Profile(**snapshot['profile'])
    # Per-component retry budgets survive pauses/restarts and stay local to this batch.
    with connect() as db:
        budgets=[]
        for item in items:
            row=db.execute('SELECT result FROM components WHERE job_id=? AND row_no=? AND category=?',
                           (job['id'],int(item['id']),category)).fetchone()
            previous=json.loads(row['result'] or '{}') if row else {}
            budgets.append(previous.get('retry_max_tokens',q.max_tokens))
    q=q.model_copy(update={'max_tokens':max([q.max_tokens,*budgets])})
    path,body,target=compile_request(task,q,profile,items,category)
    rid=uid()
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT status FROM jobs WHERE id=?',(job['id'],)).fetchone()[0]!='running':return
        # Reservation is durable before sending; a crash consumes this attempt.
        db.execute('INSERT INTO llm_requests(id,job_id,category,batch_start,inputs,request_json,status,created) VALUES(?,?,?,?,?,?,?,?)',
                   (rid,job['id'],category,int(items[0]['id']),dumps(items),dumps(body),'running',time.time()))
        for item in items:
            row=db.execute('SELECT attempts,request_ids FROM components WHERE job_id=? AND row_no=? AND category=?',(job['id'],int(item['id']),category)).fetchone()
            db.execute('UPDATE components SET attempts=attempts+1,request_ids=? WHERE job_id=? AND row_no=? AND category=?',(dumps(json.loads(row['request_ids'])+[rid]),job['id'],int(item['id']),category))
        db.execute('UPDATE jobs SET requests=requests+1 WHERE id=?',(job['id'],))
    log.debug('llm_request_started job_id=%s request_id=%s strategy=%s samples=%s',job['id'],rid,q.strategy,len(items))
    out=perform(profile,q,target,items,path,body,client)
    log.debug('llm_request_completed job_id=%s request_id=%s valid=%s samples=%s seconds=%s',job['id'],rid,sum(r['status']=='ok' for r in out['results'].values()),len(items),out['seconds'])
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('UPDATE llm_requests SET status=?,output_json=?,seconds=?,prompt_tokens=?,completion_tokens=? WHERE id=?',('finished',dumps(out),out['seconds'],out['prompt_tokens'],out['completion_tokens'],rid))
        for item in items:
            result=out['results'][item['id']]
            attempts=db.execute('SELECT attempts FROM components WHERE job_id=? AND row_no=? AND category=?',(job['id'],int(item['id']),category)).fetchone()[0]
            status=result['status']
            if status!='ok' and attempts>=q.retries+1:status='failed'
            result['status']=status
            if status!='ok':
                result['retry_max_tokens']=q.max_tokens * (2 if out.get('output_limit_reached') else 1)
                if status=='pending' and out.get('output_limit_reached'):
                    log.info('output_budget_retry job_id=%s row=%s category=%s max_tokens=%s next_max_tokens=%s',
                             job['id'],item['id'],category,q.max_tokens,result['retry_max_tokens'])
            db.execute('UPDATE components SET status=?,result=? WHERE job_id=? AND row_no=? AND category=?',(status,dumps(result),job['id'],int(item['id']),category))
        db.execute('UPDATE jobs SET prompt_tokens=prompt_tokens+?,completion_tokens=completion_tokens+?,total_seconds=total_seconds+?,updated=? WHERE id=?',(out['prompt_tokens'],out['completion_tokens'],out['seconds'],time.time(),job['id']))


def component_details(db,job_id,row_no):
    rows=db.execute('SELECT * FROM components WHERE job_id=? AND row_no=? ORDER BY category',(job_id,row_no)).fetchall()
    return [{'category':r['category'] or None,'status':r['status'],'attempts':r['attempts'],
             'request_ids':json.loads(r['request_ids']),**(json.loads(r['result']) if r['result'] else {})} for r in rows]


def aggregate(db, job, snapshot, row_no, categories):
    rows={r['category']:r for r in db.execute('SELECT * FROM components WHERE job_id=? AND row_no=?',(job['id'],row_no))}
    if len(rows)!=len(categories) or any(r['status']=='pending' for r in rows.values()):return None
    q=Query(**snapshot['query']);parts=[json.loads(rows[c]['result'] or '{}') for c in categories]
    failed=any(r['status']!='ok' for r in rows.values())
    result=dict(labels=[],rationale=None,status='failed' if failed else 'ok',error=None,raw=None,attempts=0,seconds=0,prompt_tokens=0,completion_tokens=0,evidence=[],thinking=None,attempt_outputs=[],candidate_interpretations=[],alternative_interpretations=[],self_reported_confidence=None)
    if len(categories)==1 and categories[0]=='':result.update({k:v for k,v in parts[0].items() if k not in ('status','error','retry_max_tokens')})
    else:
        result['labels']=[c for c,part in zip(categories,parts) if c in part.get('labels',[])]
        if q.rationale:result['rationale']='\n\n'.join(f'{c}: {part.get("rationale", "No valid decision")}' for c,part in zip(categories,parts))
        result['evidence']=[e for part in parts for e in part.get('evidence',[])]
        for field in ('candidate_interpretations','alternative_interpretations'):
            result[field]=[{**alt,'category':c} for c,part in zip(categories,parts) for alt in part.get(field,[])]
    result['attempts']=sum(r['attempts'] for r in rows.values())
    for c in categories:
        for rid in json.loads(rows[c]['request_ids']):
            request=db.execute('SELECT output_json,status,seconds,prompt_tokens,completion_tokens,inputs FROM llm_requests WHERE id=?',(rid,)).fetchone()
            output=json.loads(request['output_json'] or '{}')
            share=max(1,len(json.loads(request['inputs'])))
            result['seconds']+=request['seconds']/share
            # Integer token attribution is deliberately not fabricated per item.
            # Exact usage is available only on the request record.
            error=output.get('results',{}).get(str(row_no),{}).get('error') or output.get('error')
            result['attempt_outputs'].append({'request_id':rid,'category':c or None,'error':error,'status':request['status']})
    if failed:
        result['error']='; '.join((c+': ' if c else '')+p.get('error','No valid decision') for c,p in zip(categories,parts) if p.get('status')!='ok')
        result['labels']=[]
        if q.default_label and result['attempts']>0:result.update(status='fallback',labels=[q.default_label])
    return result


def run_window(job, stopping, save_result):
    snapshot=json.loads(job['snapshot'])
    if snapshot['prompt_protocol']!='experiment-v3':raise ValueError('Unsupported prompt protocol')
    q=Query(**snapshot['query']);task=Task(**snapshot['task'])
    categories=[c.id for c in task.categories] if q.strategy=='binary' else ['']
    with connect() as db:
        rows=db.execute('SELECT row_no,data FROM records WHERE dataset_id=? AND row_no>? ORDER BY row_no LIMIT ?', (job['dataset_id'],job['cursor'],q.batch_size*q.concurrency)).fetchall()
        if not rows:
            db.execute("UPDATE jobs SET status=CASE WHEN failed>0 THEN 'completed_with_errors' ELSE 'completed' END,finished_at=?,updated=? WHERE id=? AND status='running'",(time.time(),time.time(),job['id']));return
        completed={r[0] for r in db.execute('SELECT row_no FROM results WHERE job_id=? AND row_no>? AND row_no<=?',(job['id'],job['cursor'],rows[-1]['row_no']))}
        items=[]
        for row in rows:
            error=None
            try:items.append(prepare_item(row['row_no'],json.loads(row['data']),snapshot))
            except ValueError as exc:error=str(exc)
            if row['row_no'] in completed:continue
            for category in categories:
                db.execute('INSERT OR IGNORE INTO components(job_id,row_no,category,status,result) VALUES(?,?,?,?,?)',(job['id'],row['row_no'],category,'failed' if error else 'pending',dumps({'status':'failed','error':error}) if error else None))
        # Interrupted requests remain charged; do not reset retry budgets on resume.
        db.execute("UPDATE components SET status='failed',result=? WHERE job_id=? AND status='pending' AND attempts>=?",(dumps({'status':'failed','error':'Attempt budget exhausted after interrupted request'}),job['id'],q.retries+1))
    groups=list(batches(items,q))
    with httpx.Client(trust_env=False,limits=httpx.Limits(max_connections=q.concurrency,max_keepalive_connections=q.concurrency)) as client, ThreadPoolExecutor(max_workers=q.concurrency) as pool:
        while not stopping.is_set():
            work=[]
            with connect() as db:
                if db.execute('SELECT status FROM jobs WHERE id=?',(job['id'],)).fetchone()[0]!='running':break
                for category in categories:
                    pending={str(r[0]) for r in db.execute("SELECT row_no FROM components WHERE job_id=? AND category=? AND status='pending' AND row_no>? AND row_no<=?",(job['id'],category,job['cursor'],rows[-1]['row_no']))}
                    for group in groups:
                        subset=[i for i in group if i['id'] in pending]
                        if subset:work.append((category,subset))
            if not work:break
            # Bounded futures also bound stop/pause latency to in-flight calls.
            for start in range(0,len(work),q.concurrency):
                if stopping.is_set():break
                futures=[pool.submit(request_once,job,snapshot,category,group,client) for category,group in work[start:start+q.concurrency]]
                for future in futures:future.result()
                persist_ready(job,snapshot,rows,categories,save_result)
    persist_ready(job,snapshot,rows,categories,save_result)
    with connect() as db:
        remaining=db.execute("SELECT COUNT(*) FROM components WHERE job_id=? AND row_no>? AND row_no<=? AND status='pending'",(job['id'],job['cursor'],rows[-1]['row_no'])).fetchone()[0]
        if not remaining:db.execute('UPDATE jobs SET cursor=? WHERE id=?',(rows[-1]['row_no'],job['id']))


def persist_ready(job,snapshot,rows,categories,save_result):
    for row in rows:
        with connect() as db:
            if db.execute('SELECT 1 FROM results WHERE job_id=? AND row_no=?',(job['id'],row['row_no'])).fetchone():continue
            result=aggregate(db,job,snapshot,row['row_no'],categories)
        if result:save_result(job['id'],row['row_no'],result)


def request_chunks(job_ids):
    for job_id in job_ids:
        after=0
        while True:
            with connect() as db:
                rows=db.execute('SELECT rowid AS cursor,* FROM llm_requests WHERE job_id=? AND rowid>? ORDER BY rowid LIMIT 100',(job_id,after)).fetchall()
            if not rows:break
            for row in rows:
                obj=dict(row);after=obj.pop('cursor')
                for key in ('inputs','request_json','output_json'):obj[key]=json.loads(obj[key]) if obj[key] else None
                yield dumps(obj)+'\n'
