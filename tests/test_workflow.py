import json
import pytest
from fastapi.testclient import TestClient
from textlab.api import app
from textlab.worker import tick

TASK={'name':'Instrument','instructions':'Choose a class.','categories':[{'label':'A','definition':'Alpha'},{'label':'B','definition':'Beta'}]}

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('TEXTLAB_DATA',str(tmp_path))
    with TestClient(app) as c:yield c


def prepare(c):
    did=c.post('/api/datasets',content=b'doc_id,text,gold_label\n1,Alpha,A\n2,Beta,B\n').json()['id'];tick()
    tid=c.post('/api/tasks',json=TASK).json()['id']
    pid=c.post('/api/profiles',json={'name':'Saved server','provider':'mock','base_url':'http://localhost'}).json()['id']
    gid=c.post('/api/gold-sets',json={'name':'Gold','dataset_id':did}).json()['id']
    e=c.post('/api/evaluations',json={'name':'Validation','task_id':tid,'gold_id':gid,'variants':[{'name':'Config','profile_id':pid,'query':{'model':'m','temperature':.7,'seed':42,'evidence':True,'thinking':'off'}}]}).json()
    return did,tid,pid,e['job_ids'][0]


def test_prediction_reuses_evaluated_snapshot_after_library_deletion(client):
    did,tid,pid,jid=prepare(client)
    for _ in range(10):tick()
    old=client.get('/api/jobs/'+jid).json()['snapshot']
    client.put('/api/tasks/'+tid+'?revision=1',json={**TASK,'name':'Changed instrument'})
    client.delete('/api/tasks/'+tid);client.delete('/api/profiles/'+pid)
    target=client.post('/api/datasets',content=b'body\nNew corpus text\n').json()['id'];tick()
    request={'name':'Application','dataset_id':target,'task_ids':[tid],'profile_id':'snapshot','text_column':'body','query':old['query'],'source_evaluation_job_id':jid}
    response=client.post('/api/predictions',json=request)
    assert response.status_code==201,response.text
    job=client.get('/api/jobs/'+response.json()['job_ids'][0]).json();s=job['snapshot']
    assert s['task']==old['task'] and s['task_revision']==1 and s['profile']==old['profile']
    assert s['query']==old['query'] and s['text_column']=='body' and s['source_evaluation_job_id']==jid
    assert s['source_evaluation_id']==old['evaluation_id']
    assert client.get('/api/jobs/'+jid).json()['snapshot']==old
    for _ in range(10):tick()
    assert client.get('/api/predictions/'+response.json()['id']).json()['status']=='completed'
    items=client.get('/api/jobs').json()
    assert next(r for r in items if r['id']==jid)['evaluation_id']==old['evaluation_id']
    assert next(r for r in items if r['id']==job['id'])['prediction_id']==response.json()['id']


def test_reuse_requires_completed_evaluation_and_matching_task(client):
    did,tid,pid,jid=prepare(client)
    request={'name':'Apply','dataset_id':did,'task_ids':[tid],'profile_id':pid,'text_column':'text','query':{'model':'m'},'source_evaluation_job_id':jid}
    assert client.post('/api/predictions',json=request).status_code==409
    for _ in range(10):tick()
    assert client.post('/api/predictions',json={**request,'task_ids':['wrong']}).status_code==422
    plain=client.post('/api/jobs',json={'name':'Individual','dataset_id':did,'task_id':tid,'profile_id':pid,'text_column':'text','query':{'model':'m'}}).json()['id']
    for _ in range(10):tick()
    assert client.post('/api/predictions',json={**request,'source_evaluation_job_id':plain}).status_code==422
    assert client.get('/api/predictions').json()==[]
