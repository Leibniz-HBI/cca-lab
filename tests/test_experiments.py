import json
import sqlite3
import threading
import httpx
import pytest
from fastapi.testclient import TestClient
from cca_lab.api import app
from cca_lab.db import connect,init,SCHEMA,dumps
from cca_lab.models import Task,Query,Profile
from cca_lab.experiment import compile_request,perform,prepare_item
from cca_lab.worker import tick,recover_interrupted_work
from task_fixtures import task_spec

BOOK=task_spec(mode='multi',categories=[{'label':'A','definition':'Only definition ALPHA'},{'label':'B','definition':'Only definition BETA'}],examples=[{'text':'Alpha sample','labels':['A'],'context':'Example context','explanation':'A and B are alternatives'}])

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('CCA_LAB_DATA',str(tmp_path))
    with TestClient(app) as c:yield c


def setup(c,query=None,rows=b'doc_id,text,gold_label,context\n1,Alpha,A,Prior\n2,Beta,B,\n3,Neither,,Other\n'):
    d=c.post('/api/datasets',content=rows).json()['id'];tick()
    t=c.post('/api/tasks',json=BOOK).json()['id'];p=c.post('/api/profiles',json={'name':'mock','provider':'mock'}).json()['id']
    g=c.post('/api/gold-sets',json={'name':'Gold','dataset_id':d,'mode':'multi','allow_empty':True,'context_column':'context'}).json()['id']
    q={'model':'mock',**(query or {})}
    return d,t,p,g,q


def finish(c,eid):
    for _ in range(15):
        tick()
        report=c.get('/api/evaluations/'+eid+'/report')
        if report.status_code==200:return report.json()
    raise AssertionError(c.get('/api/evaluations/'+eid).text)

@pytest.mark.parametrize('provider',['openai','ollama'])
@pytest.mark.parametrize('strategy',['joint','binary'])
@pytest.mark.parametrize('batch_size',[1,3])
@pytest.mark.parametrize('context',[False,True])
def test_compiler_matrix(provider,strategy,batch_size,context):
    task=Task(**BOOK);q=Query(model='m',strategy=strategy,batch_size=batch_size,use_context=context,rationale=True,evidence=True,alternatives=True,confidence=True)
    items=[{'id':str(i),**({'context':'Prior '+str(i)} if context else {}),'text':'Text '+str(i)} for i in range(batch_size)]
    path,body,target=compile_request(task,q,Profile(name='p',provider=provider),items,'A' if strategy=='binary' else '')
    assert body['messages'][-1]['content']==dumps({'samples':items})
    assert [x['role'] for x in body['messages']]==['system','user','assistant','user']
    demo=json.loads(body['messages'][2]['content'])['results'][0]
    assert 'confidence' not in demo and 'evidence' not in demo
    if strategy=='binary':
        assert 'Only definition BETA' not in dumps(body)
        assert 'explanation' not in demo
    schema=body['format'] if provider=='ollama' else body['response_format']['json_schema']['schema']
    assert schema['properties']['results']['minItems']==batch_size
    if context:assert body['messages'][-1]['content'].index('context')<body['messages'][-1]['content'].index('text')
    assert (body.get('max_tokens') or body['options']['num_predict'])==8192
    assert q.retries==3 and q.seed==9721


def test_local_validation_partial_ids_quotes_and_empty():
    task=Task(**BOOK);q=Query(model='m',batch_size=2,evidence=True,use_context=True)
    profile=Profile(name='p',base_url='http://localhost')
    items=[{'id':'1','context':'Not target','text':'Alpha'},{'id':'2','context':'','text':'Beta'}]
    path,body,t=compile_request(task,q,profile,items)
    def run(results):
        response={'choices':[{'message':{'content':dumps({'results':results})}}],'usage':{'prompt_tokens':20,'completion_tokens':10}}
        with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json=response))) as client:return perform(profile,q,t,items,path,body,client)
    out=run([{'id':'2','labels':[],'evidence':[]},{'id':'1','labels':['A'],'evidence':[{'label':'A','quote':'Not target'}]}])
    assert out['results']['2']['status']=='ok' and out['results']['1']['status']=='pending'
    out=run([{'id':'1','labels':[],'evidence':[]},{'id':'1','labels':[],'evidence':[]}])
    assert all(r['status']=='pending' for r in out['results'].values())
    out=run([{'id':'unexpected','labels':[],'evidence':[]}]);assert out['error']


def create_eval(c,t,p,g,q):
    response=c.post('/api/evaluations',json={'name':'Experiment','task_id':t,'gold_id':g,'variants':[{'name':'v','profile_id':p,'query':q}]})
    assert response.status_code==201,response.text
    return response.json()


def test_binary_batch_context_metrics_exports(client):
    d,t,p,g,q=setup(client,{'strategy':'binary','batch_size':2,'use_context':True,'evidence':True,'rationale':True,'confidence':True,'alternatives':True})
    e=create_eval(client,t,p,g,q);report=finish(client,e['id']);job=client.get('/api/jobs/'+e['job_ids'][0]).json()
    assert job['requests']==4 and job['done']==3 and job['failed']==0
    assert job['query_count']['planned']==4 and job['snapshot']['query']['seed']==9721
    assert set(job['snapshot']['task'])=={'codebook'}
    rows=client.get('/api/jobs/'+job['id']+'/results').json()
    assert rows[0]['labels']==['A','B'] and len(rows[0]['component_results'])==2
    assert rows[0]['self_reported_confidence'] is None
    assert set(report['groups'][0]['binary_confidence'])=={'A','B'}
    assert client.get('/api/evaluations/'+e['id']+'/confidence-chart?category=A').status_code==200
    assert client.get('/api/jobs/'+job['id']+'/export?format=parquet').status_code==200
    requests=client.get('/api/jobs/'+job['id']+'/requests').json()
    assert len(requests)==4 and any(i.get('context')=='Prior' for req in requests for i in req['inputs'])
    assert len(client.get('/api/jobs/'+job['id']+'/requests.jsonl').text.splitlines())==4


def test_partial_retry_preserves_valid_and_costs(client,monkeypatch):
    d,t,p,g,q=setup(client,{'batch_size':3})
    import cca_lab.executor as ex
    real=ex.perform;calls=[]
    def fake(profile,query,task,items,path,body,http):
        calls.append([i['id'] for i in items]);out=real(profile,query,task,items,path,body,http)
        if len(calls)==1:out['results']['1']={'status':'pending','error':'Invalid output'}
        out.update(prompt_tokens=12,completion_tokens=6,seconds=2);return out
    monkeypatch.setattr(ex,'perform',fake)
    e=create_eval(client,t,p,g,q);finish(client,e['id']);job=client.get('/api/jobs/'+e['job_ids'][0]).json()
    assert calls==[['1','2','3'],['1']]
    assert job['requests']==2 and job['prompt_tokens']==24 and job['completion_tokens']==12 and job['total_seconds']==4
    assert job['failed']==0
    errors=client.get('/api/jobs/'+job['id']+'/errors').json();assert errors['total']==1
    assert errors['rows'][0]['attempt_outputs'][0]['error']=='Invalid output'


def test_binary_failure_not_negative_and_fallback(client,monkeypatch):
    d,t,p,g,q=setup(client,{'strategy':'binary','batch_size':3,'retries':1,'default_label':'A'})
    import cca_lab.executor as ex
    real=ex.perform;calls=[]
    def fake(profile,query,task,items,path,body,http):
        calls.append(task.categories[0].id);out=real(profile,query,task,items,path,body,http)
        if task.categories[0].id=='B':out['results']={i['id']:{'status':'pending','error':'Bad B'} for i in items}
        return out
    monkeypatch.setattr(ex,'perform',fake)
    e=create_eval(client,t,p,g,q);finish(client,e['id']);job=client.get('/api/jobs/'+e['job_ids'][0]).json()
    assert calls.count('A')==1 and calls.count('B')==2
    assert job['failed']==job['fallback_count']==3
    rows=client.get('/api/jobs/'+job['id']+'/results').json();assert all(r['status']=='fallback' and r['labels']==['A'] for r in rows)
    assert all(len(r['component_results'])==2 for r in rows)


def test_pause_resume_keeps_valid_components(client,monkeypatch):
    d,t,p,g,q=setup(client,{'batch_size':3})
    import cca_lab.executor as ex
    real=ex.perform;calls=[];jobid=None
    def fake(profile,query,task,items,path,body,http):
        calls.append([i['id'] for i in items]);out=real(profile,query,task,items,path,body,http)
        if len(calls)==1:
            out['results']['1']={'status':'pending','error':'Retry me'}
            with connect() as db:db.execute("UPDATE jobs SET status='pausing' WHERE id=?",(jobid,))
        return out
    monkeypatch.setattr(ex,'perform',fake)
    e=create_eval(client,t,p,g,q);jobid=e['job_ids'][0];tick();tick()
    assert client.get('/api/jobs/'+jobid).json()['status']=='paused'
    recover_interrupted_work()
    assert client.post('/api/jobs/'+jobid+'/resume').status_code==200
    finish(client,e['id']);assert calls==[['1','2','3'],['1']]


def test_prediction_variants_and_context_mapping_guard(client):
    d,t,p,g,q=setup(client,{'batch_size':2,'use_context':True})
    assert client.post('/api/jobs',json={'name':'No mapping','dataset_id':d,'task_id':t,'profile_id':p,'text_column':'text','query':q}).status_code==422
    response=client.post('/api/predictions',json={'name':'Predict','dataset_id':d,'task_ids':[t],'text_column':'text','context_column':'context','variants':[{'name':'joint','profile_id':p,'query':q,'seeds':[9721,9722]},{'name':'binary','profile_id':p,'query':{**q,'strategy':'binary'}}]})
    assert response.status_code==201,response.text
    pid=response.json()['id']
    for _ in range(15):tick()
    info=client.get('/api/predictions/'+pid).json();assert info['artifact_status']=='ready',info
    assert len(info['runs'])==3 and info['query_count']['planned']==8
    for fmt in ['csv','json','jsonl','parquet','requests']:assert client.get('/api/predictions/'+pid+'/download/'+fmt).status_code==200
    preview=client.post('/api/experiments/preview',json={'task_id':t,'dataset_id':d,'profile_id':p,'text_column':'text','context_column':'context','query':q})
    assert preview.status_code==200,preview.text
    inputs=json.loads(preview.json()['request']['messages'][-1]['content'])['samples'];assert len(inputs)==2 and inputs[0]['context']=='Prior'




def test_rejected_input_has_no_fallback(client):
    d,t,p,g,q=setup(client,{'max_text_chars':1,'default_label':'A'})
    e=create_eval(client,t,p,g,q);finish(client,e['id'])
    job=client.get('/api/jobs/'+e['job_ids'][0]).json()
    assert job['requests']==0 and job['failed']==3 and job['fallback_count']==0


def test_interrupted_attempt_consumes_budget(client,monkeypatch):
    import cca_lab.executor as ex
    d,t,p,g,q=setup(client,{'batch_size':3,'retries':0})
    e=create_eval(client,t,p,g,q);jid=e['job_ids'][0]
    with connect() as db:
        db.execute("UPDATE jobs SET status='running' WHERE id=?",(jid,))
        job=dict(db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
    def crash(*args):raise RuntimeError('Process lost after request reservation')
    monkeypatch.setattr(ex,'perform',crash)
    from cca_lab.worker import save_result
    with pytest.raises(RuntimeError):ex.run_window(job,threading.Event(),save_result)
    recover_interrupted_work()
    finish(client,e['id'])
    job=client.get('/api/jobs/'+jid).json()
    assert job['requests']==1 and job['failed']==3
    requests=client.get('/api/jobs/'+jid+'/requests').json()
    assert len(requests)==1 and requests[0]['status']=='interrupted'
    assert all(r['attempts']==1 for r in client.get('/api/jobs/'+jid+'/results').json())


@pytest.mark.parametrize('code,status',[(400,'failed'),(401,'failed'),(429,'pending'),(503,'pending')])
def test_http_failures_redacted_and_classified(code,status):
    q=Query(model='m');profile=Profile(name='p',base_url='http://localhost');items=[{'id':'1','text':'Alpha'}]
    path,body,t=compile_request(Task(**BOOK),q,profile,items)
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(code,text='Sensitive server response'))) as client:
        result=perform(profile,q,t,items,path,body,client)
    assert result['error']==f'HTTP {code}' and result['results']['1']['status']==status


@pytest.mark.parametrize('provider,field',[('ollama','thinking'),('openai','reasoning'),('openai','reasoning_content'),('openai','thinking')])
def test_current_requests_preserve_thinking(provider,field):
    q=Query(model='m');profile=Profile(name='p',provider=provider,base_url='http://localhost');items=[{'id':'1','text':'Alpha'}]
    path,body,t=compile_request(Task(**BOOK),q,profile,items)
    message={'content':dumps({'results':[{'id':'1','labels':['A']}]}),field:'Returned thinking'}
    response={'message':message} if provider=='ollama' else {'choices':[{'message':message}]}
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json=response))) as client:
        out=perform(profile,q,t,items,path,body,client)
    assert out['thinking']=='Returned thinking' and out['results']['1']['status']=='ok'


def test_current_requests_extract_inline_thinking():
    q=Query(model='m');profile=Profile(name='p',base_url='http://localhost');items=[{'id':'1','text':'Alpha'}]
    path,body,t=compile_request(Task(**BOOK),q,profile,items)
    raw='<think>Returned trace</think>'+dumps({'results':[{'id':'1','labels':[]}]})
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'choices':[{'message':{'content':raw}}]}))) as client:
        out=perform(profile,q,t,items,path,body,client)
    assert out['thinking']=='Returned trace' and out['content']==raw and out['results']['1']['status']=='ok'


def test_cancellation_drains_current_request(client,monkeypatch):
    import cca_lab.executor as ex
    d,t,p,g,q=setup(client,{'batch_size':1,'concurrency':1})
    e=create_eval(client,t,p,g,q);jid=e['job_ids'][0];original=ex.perform;calls=[]
    def cancel(profile,query,task,items,path,body,http):
        calls.append(items)
        out=original(profile,query,task,items,path,body,http)
        with connect() as db:db.execute("UPDATE jobs SET status='cancelling' WHERE id=?",(jid,))
        return out
    monkeypatch.setattr(ex,'perform',cancel)
    tick();tick()
    job=client.get('/api/jobs/'+jid).json()
    assert job['status']=='cancelled' and job['done']==1 and job['requests']==1 and len(calls)==1
