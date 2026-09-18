import json
import httpx
import pytest
from fastapi.testclient import TestClient
from textlab.api import app
from textlab.models import Task, Query, validate_labels
from textlab.llm import output_schema, messages, parse_result, mock_response, classify, selected_examples
from textlab.worker import tick
from textlab.reports import metric_rows, confidence_rows, render_chart
from task_fixtures import task_spec as make_task

def task_spec(**kwargs):
    return make_task(categories=[{"label":"A","definition":"Alpha"},{"label":"B","definition":"Beta"}],**kwargs)

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('TEXTLAB_DATA', str(tmp_path))
    with TestClient(app) as c: yield c


def test_empty_multilabel_validation_schema_and_examples():
    t=Task(**task_spec(mode='multi',evidence=True,alternatives=True,rationale=True,confidence=True))
    validate_labels([],t)
    obj=mock_response(t,'Nothing applies',[],'No category applies')
    assert parse_result(json.dumps(obj),t,'Nothing applies')['labels']==[]
    assert output_schema(t)['properties']['labels']['minItems']==0
    assert output_schema(t)['properties']['candidate_interpretations']['items']['properties']['labels']['minItems']==0
    assert 'zero or more' in messages(t,Query(model='m'),'Text')[0]['content']
    assert not selected_examples(t,Query(model='m',examples_per_category=0))
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(obj)}}]}))) as http:
        result=classify({'task':t.model_dump(),'query':{'model':'m','retries':0},'profile':{'name':'P','base_url':'http://localhost'}},'Nothing applies',http)
    assert result['status']=='ok' and result['labels']==[] and result['attempts']==1
    single=Task(**task_spec())
    with pytest.raises(ValueError):validate_labels([],single)


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
    import textlab.worker as w
    original=w.classify
    def empty(snapshot,text,http):
        result=original(snapshot,text,http)
        if text=='None applies':result['labels']=[]
        return result
    monkeypatch.setattr(w,'classify',empty)
    response=client.post('/api/evaluations',json={'name':'Empty labels','gold_id':g,'task_id':t,'variants':[{'name':'One run','profile_id':p,'query':{'model':'mock'}}]})
    assert response.status_code==201,response.text
    eid=response.json()['id']
    revision=client.put('/api/gold-sets/'+g,json={**spec,'name':'Revised','gold_column':'alternate'}).json()
    assert revision['id']!=g and revision['revised_from']==g
    assert client.get('/api/gold-sets/'+g+'/preview').json()==before
    assert client.get('/api/gold-sets/'+revision['id']+'/preview').json()[0]['gold_labels']==['A']
    for _ in range(6):tick()
    from textlab.eval_api import ready_report
    report=ready_report(eid)
    group=report['scopes']['common']['groups'][0]
    assert group['summary']['accuracy']==1 and group['coverage']==1
    for classes in [False,True]:
        assert all(not any(k.endswith('_sd') for k in r) for r in metric_rows(report,'common',classes))
    assert all(not any(k.endswith('_sd') for k in r) for r in confidence_rows(report,'common'))
    assert 'sample SD' not in render_chart(report,'common','overview','accuracy').decode()
    assert 'sample SD' not in render_chart(report,'common','classes','f1').decode()
    assert client.put('/api/gold-sets/missing',json=spec).status_code==404
