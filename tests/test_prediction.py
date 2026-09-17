import csv
import io
import json
from pathlib import Path

import httpx
import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient

from textlab.api import app
from textlab.db import connect, init, root
from textlab.llm import classify
from textlab.models import Profile
from textlab.thinking import thinking_body
from textlab.runtime import timed_batch, runtime_metrics
from textlab.worker import tick

TASK={'name':'Topic','instructions':'Classify the text.','categories':[{'label':'A','definition':'Alpha'},{'label':'B','definition':'Beta'}]}

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('TEXTLAB_DATA',str(tmp_path))
    with TestClient(app) as c:yield c


def setup(client):
    did=client.post('/api/datasets?filename=sample.csv',content=b'doc_id,text,gold_label\n001,Alpha,A\n002,Beta,B\n').json()['id'];tick()
    tasks=[client.post('/api/tasks',json={**TASK,'name':name,'thinking':thinking,'rationale':True,'evidence':True}).json()['id'] for name,thinking in [('Topic','off'),('Position','high')]]
    profile=client.post('/api/profiles',json={'name':'Demo','provider':'mock','base_url':'http://localhost'}).json()['id']
    return did,tasks,profile


def predict(client,did,tasks,profile):
    response=client.post('/api/predictions',json={'name':'Two tasks','dataset_id':did,'task_ids':tasks,'profile_id':profile,'text_column':'text','query':{'model':'demo','concurrency':2}})
    assert response.status_code==201,response.text
    return response.json()['id']


def finish(client,id):
    for _ in range(20):
        tick();p=client.get('/api/predictions/'+id).json()
        assert p['artifact_status']!='failed',p
        if p['artifact_status']=='ready':return p
    raise AssertionError('Not finished')


def test_multitask_durable_formats_and_snapshots(client):
    did,tasks,profile=setup(client);id=predict(client,did,tasks,profile)
    # Mutating/deleting library records must not alter queued snapshots.
    assert client.delete('/api/profiles/'+profile).status_code==200
    assert client.put('/api/tasks/'+tasks[0]+'?revision=1',json={**TASK,'name':'Changed'}).status_code==200
    p=finish(client,id)
    assert p['status']=='completed' and p['done']==4 and len(p['artifacts'])==7
    assert [r['snapshot']['task']['thinking'] for r in p['runs']]==['off','high']
    assert p['runs'][0]['task_name']=='Topic'
    for r in p['runs']:
        assert r['runtime']['active_seconds']>0 and r['runtime']['documents_per_second']>0
    folder=root()/'predictions'/id
    assert folder.is_dir()
    original=(folder/'results.json').read_bytes()
    init() # simulate re-opening persistent data
    assert client.get('/api/predictions/'+id+'/download/json').content==original
    rows=json.loads(original);assert len(rows)==4
    assert [r['source']['doc_id'] for r in rows]==['001','002','001','002']
    assert {r['task_id'] for r in rows}==set(tasks)
    assert rows[0]['labels']==['A'] and rows[0]['rationale'] and rows[0]['evidence'][0]['quote']=='Alpha'
    assert len(client.get('/api/predictions/'+id+'/download/jsonl').text.splitlines())==4
    response=client.get('/api/predictions/'+id+'/download/csv')
    csvrows=list(csv.DictReader(io.StringIO(response.content.decode('utf-8-sig'))))
    assert len(csvrows)==4 and csvrows[0]['prediction.labels']=='["A"]'
    table=pq.read_table(io.BytesIO(client.get('/api/predictions/'+id+'/download/parquet').content))
    assert table.num_rows==4 and table['source.doc_id'].to_pylist()==['001','002','001','002']
    manifest=client.get('/api/predictions/'+id+'/download/manifest').json()
    assert len(manifest['runs'])==2 and manifest['framework_version']=='0.7.0'
    assert client.delete('/api/predictions/'+id).status_code==200
    assert not folder.exists() and client.get('/api/jobs').json()==[]


def test_cancel_exports_unprocessed_and_active_delete_guard(client):
    did,tasks,profile=setup(client);id=predict(client,did,tasks,profile)
    assert client.delete('/api/predictions/'+id).status_code==409
    assert client.delete('/api/datasets/'+did+'?cascade=true').status_code==409
    assert client.post('/api/predictions/'+id+'/pause').status_code==200;tick()
    assert client.get('/api/predictions/'+id).json()['status']=='paused'
    assert client.post('/api/predictions/'+id+'/resume').status_code==200
    assert client.post('/api/predictions/'+id+'/cancel').status_code==200
    p=finish(client,id);assert p['status']=='cancelled'
    rows=client.get('/api/predictions/'+id+'/download/json').json()
    assert len(rows)==4 and all(r['status']=='not_processed' and r['labels'] is None for r in rows)


def test_delete_csv_preserves_records_and_dataset_cascade(client):
    did,tasks,profile=setup(client)
    gid=client.post('/api/gold-sets',json={'name':'Gold','dataset_id':did}).json()['id']
    eid=client.post('/api/evaluations',json={'name':'E','gold_id':gid,'task_id':tasks[0],'variants':[{'name':'v','profile_id':profile,'query':{'model':'demo'}}]}).json()['id']
    pid=predict(client,did,tasks,profile)
    assert client.delete('/api/gold-sets/'+gid).status_code==409
    assert client.delete('/api/gold-sets/'+gid+'?cascade=true').status_code==409
    assert client.delete('/api/evaluations/'+eid).status_code==409
    assert client.delete('/api/datasets/'+did+'/csv').status_code==200
    assert client.get('/api/datasets').json()[0]['csv_available'] is False
    assert len(client.get('/api/datasets/'+did+'/preview').json())==2
    finish(client,pid)
    assert client.delete('/api/datasets/'+did).status_code==409
    deps=client.get('/api/datasets/'+did+'/dependencies').json()
    assert len(deps['jobs'])==3 and len(deps['evaluations'])==1
    assert client.delete('/api/datasets/'+did+'?cascade=true').status_code==200
    for endpoint in ('datasets','gold-sets','evaluations','predictions','jobs'):
        assert client.get('/api/'+endpoint).json()==[]
    assert not (root()/'predictions'/pid).exists()


@pytest.mark.parametrize('provider,adapter,level,expected',[
 ('ollama','auto','off',{'think':False}),('ollama','auto','high',{'think':'high'}),
 ('openai','auto','off',{'reasoning_effort':'none'}),('openai','auto','low',{'reasoning_effort':'low'}),
 ('openai','chat_template','off',{'chat_template_kwargs':{'enable_thinking':False}}),
 ('openai','chat_template','on',{'chat_template_kwargs':{'enable_thinking':True}})])
def test_thinking_sent_to_provider(provider,adapter,level,expected):
    calls=[]
    def handle(req):
        calls.append(json.loads(req.content));message={'content':'{"labels":["A"]}','thinking':'trace','reasoning_content':'trace'}
        return httpx.Response(200,json={'message':message} if provider=='ollama' else {'choices':[{'message':message}]})
    snapshot={'task':{**TASK,'thinking':level},'query':{'model':'m','retries':0},'profile':{'name':'P','provider':provider,'thinking_adapter':adapter,'base_url':'http://localhost'}}
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:r=classify(snapshot,'Alpha',http)
    assert r['status']=='ok' and r['thinking']=='trace'
    assert all(calls[0][k]==v for k,v in expected.items())


def test_thinking_conflicts_and_override():
    p=Profile(name='P',provider='openai',thinking_adapter='chat_template')
    with pytest.raises(ValueError):thinking_body(p,'high',{})
    with pytest.raises(ValueError):thinking_body(p,'off',{'chat_template_kwargs':{'enable_thinking':True}})
    p.thinking_adapter='auto'
    with pytest.raises(ValueError):thinking_body(p,'off',{'reasoning_effort':'high'})
    assert thinking_body(p,'default',{})=={}
    from textlab.jobs import resolved_task
    from textlab.models import Query, Task
    assert resolved_task(Task(**{**TASK,'thinking':'high'}),Query(model='m',thinking='off')).thinking=='off'


def test_runtime_excludes_pause_and_marks_legacy_unknown(client,monkeypatch):
    did,tasks,profile=setup(client);pid=predict(client,did,tasks,profile)
    job=client.get('/api/predictions/'+pid).json()['runs'][0]
    with connect() as db:db.execute("UPDATE jobs SET status='running' WHERE id=?",(job['id'],))
    clock={'wall':1000.,'mono':50.}
    monkeypatch.setattr('textlab.runtime.time.time',lambda:clock['wall'])
    monkeypatch.setattr('textlab.runtime.time.monotonic',lambda:clock['mono'])
    def batch(job):clock['wall']+=2;clock['mono']+=2
    timed_batch(job,batch)
    clock['wall']+=100;clock['mono']+=100 # pause
    timed_batch(job,batch)
    with connect() as db:
        db.execute('UPDATE jobs SET done=2,total_seconds=6,finished_at=? WHERE id=?',(clock['wall'],job['id']))
        j=dict(db.execute('SELECT * FROM jobs WHERE id=?',(job['id'],)).fetchone())
    m=runtime_metrics(j)
    assert m['active_seconds']==4 and m['elapsed_seconds']==104
    assert m['documents_per_second']==.5 and m['mean_document_seconds']==3
    j['runtime_complete']=0
    assert runtime_metrics(j)['active_seconds'] is None


def test_evaluation_runtime_in_report_csv_and_chart(client):
    did,tasks,profile=setup(client)
    gid=client.post('/api/gold-sets',json={'name':'Gold','dataset_id':did}).json()['id']
    eid=client.post('/api/evaluations',json={'name':'Runtime comparison','gold_id':gid,'task_id':tasks[0],'variants':[{'name':'v','profile_id':profile,'query':{'model':'demo'}}]}).json()['id']
    for _ in range(10):tick()
    report=client.get('/api/evaluations/'+eid+'/report').json()
    assert report['runs'][0]['runtime']['active_seconds']>0
    assert 'active_seconds' in client.get('/api/evaluations/'+eid+'/report?format=csv').text
    assert client.get('/api/evaluations/'+eid+'/chart?metric=active_seconds').status_code==200
    assert client.get('/api/evaluations/'+eid+'/chart?metric=documents_per_second').status_code==200
    assert client.delete('/api/gold-sets/'+gid+'?cascade=true').status_code==200
    assert client.get('/api/datasets').json()
