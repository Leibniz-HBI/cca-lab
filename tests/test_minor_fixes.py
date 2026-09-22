import json
import httpx
import pytest
from fastapi.testclient import TestClient
from cca_lab.api import app
from cca_lab.models import Task, Query, validate_labels
from cca_lab.llm import output_schema, messages, parse_result, mock_response, selected_examples
from cca_lab.worker import tick
from cca_lab.reports import metric_rows, confidence_rows, render_chart
from task_fixtures import task_spec as make_task

def task_spec(**kwargs):
    return make_task(categories=[{"label":"A","definition":"Alpha"},{"label":"B","definition":"Beta"}],**kwargs)

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('CCA_LAB_DATA', str(tmp_path))
    with TestClient(app) as c: yield c




def prepare(c):
    d=c.post('/api/datasets?filename=empty.csv',content=b'doc_id,text,gold_label,alternate\n1,None applies,,A\n2,Alpha,A,A\n').json()['id'];tick()
    spec={'name':'Gold','dataset_id':d,'mode':'multi','allow_empty':True}
    g=c.post('/api/gold-sets',json=spec);assert g.status_code==201,g.text
    t=c.post('/api/tasks',json=task_spec(mode='multi')).json()['id']
    p=c.post('/api/profiles',json={'name':'Mock','provider':'mock'}).json()['id']
    return g.json()['id'],spec,t,p


def test_gold_edit_atomic_and_evaluation_history_preserved(client,monkeypatch):
    g,spec,t,p=prepare(client)
    assert client.put('/api/gold-sets/'+g,json={**spec,'name':'Edited'}).json()['id']==g
    before=client.get('/api/gold-sets/'+g+'/preview').json()
    assert client.put('/api/gold-sets/'+g,json={**spec,'allow_empty':False}).status_code==422
    assert client.get('/api/gold-sets/'+g+'/preview').json()==before
    import cca_lab.executor as w
    original=w.perform
    def empty(profile,query,task,items,path,body,http):
        result=original(profile,query,task,items,path,body,http)
        for item in items:
            if item['text']=='None applies':result['results'][item['id']]['labels']=[]
        return result
    monkeypatch.setattr(w,'perform',empty)
    response=client.post('/api/evaluations',json={'name':'Empty labels','gold_id':g,'task_id':t,'variants':[{'name':'One run','profile_id':p,'query':{'model':'mock'}}]})
    assert response.status_code==201,response.text
    eid=response.json()['id']
    revision=client.put('/api/gold-sets/'+g,json={**spec,'name':'Revised','gold_column':'alternate'}).json()
    assert revision['id']!=g and revision['revised_from']==g
    assert client.get('/api/gold-sets/'+g+'/preview').json()==before
    assert client.get('/api/gold-sets/'+revision['id']+'/preview').json()[0]['gold_labels']==['A']
    for _ in range(6):tick()
    from cca_lab.eval_api import ready_report
    report=ready_report(eid)
    group=report['scopes']['common']['groups'][0]
    assert group['summary']['accuracy']==1 and group['coverage']==1
    for classes in [False,True]:
        assert all(not any(k.endswith('_sd') for k in r) for r in metric_rows(report,'common',classes))
    assert all(not any(k.endswith('_sd') for k in r) for r in confidence_rows(report,'common'))
    assert 'sample SD' not in render_chart(report,'common','overview','accuracy').decode()
    assert 'sample SD' not in render_chart(report,'common','classes','f1').decode()
    assert client.put('/api/gold-sets/missing',json=spec).status_code==404
