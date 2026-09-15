import csv
import io
import json
import sqlite3
import zipfile

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sklearn.metrics import (accuracy_score,precision_recall_fscore_support,cohen_kappa_score,
    matthews_corrcoef,hamming_loss,jaccard_score)

from textlab.api import app
from textlab.db import connect,init
from textlab.evaluation import score
from textlab.llm import classify,parse_result,output_schema
from textlab.models import Task,GoldSet
from textlab.worker import tick

TASK={'name':'Topic','instructions':'Select labels from the text.','categories':[{'label':'A','definition':'A'},{'label':'B','definition':'B'},{'label':'C','definition':'C'}]}

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('TEXTLAB_DATA',str(tmp_path))
    with TestClient(app) as c:
        yield c


def setup(client,multi=False,content=None):
    content=content or b'document,body,annotation\n001,Alpha,A\n002,Beta,B\n003,Gamma,C\n004,Delta,A\n'
    did=client.post('/api/datasets',content=content).json()['id'];tick()
    r=client.post('/api/gold-sets',json={'name':'Gold','dataset_id':did,'doc_id_column':'document','text_column':'body','gold_column':'annotation','mode':'multi' if multi else 'single','separator':'|','allow_empty':multi})
    assert r.status_code==201,r.text
    gold=r.json()['id']
    task=client.post('/api/tasks',json={**TASK,'mode':'multi' if multi else 'single','allow_empty':multi}).json()['id']
    profile=client.post('/api/profiles',json={'name':'Mock','provider':'mock','base_url':'http://localhost'}).json()['id']
    return gold,task,profile,did


def evaluate(client,gold,task,profile,variants=None):
    variants=variants or [{'name':'T=0','profile_id':profile,'query':{'model':'mock','temperature':0,'rationale':True,'evidence':True}},{'name':'T=.5','profile_id':profile,'query':{'model':'mock','temperature':.5}}]
    response=client.post('/api/evaluations',json={'name':'Comparison','gold_id':gold,'task_id':task,'variants':variants})
    assert response.status_code==201,response.text
    id=response.json()['id']
    for _ in range(30):
        tick();state=client.get('/api/evaluations/'+id).json()
        if state['report_ready']:
            return id,state
        assert not state['report_error'],state
    raise AssertionError('No report')


def test_evaluation_pipeline_reports_and_predictions(client):
    gold,task,profile,_=setup(client)
    id,state=evaluate(client,gold,task,profile)
    assert state['status']=='completed' and len(state['runs'])==2
    report=client.get('/api/evaluations/'+id+'/report').json()
    assert report['common_n']==4
    for r in report['runs']:
        assert r['summary']['accuracy']==.5
        assert r['summary']['f1_macro']==pytest.approx((2/3)/3)
        assert r['coverage']==1 and r['accuracy_all']==.5
    rows=client.get(f"/api/evaluations/{id}/predictions?job_id={state['runs'][0]['id']}").json()
    assert rows[0]['doc_id']=='001' and rows[0]['gold_labels']==['A']
    assert rows[0]['evidence']==[{'label':'A','quote':'Alpha','start':0,'end':5}]
    assert rows[0]['rationale']
    assert rows[0]['predicted_labels']==['A']
    for format in ('csv','class_csv','html','json','zip'):
        response=client.get(f'/api/evaluations/{id}/report?format={format}')
        assert response.status_code==200,response.text[:300]
        if format=='zip':
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                assert {'report.html','report.json','metrics.csv','per_class.csv','predictions.csv','overview.png','classes.svg','confusion-01.svg'}<=set(z.namelist())
                assert z.testzip() is None
                assert len(list(csv.DictReader(io.StringIO(z.read('predictions.csv').decode('utf-8-sig')))))==8
    assert client.get(f'/api/evaluations/{id}/chart?kind=confusion').status_code==200
    assert client.get(f'/api/evaluations/{id}/chart?metric=bad').status_code==422
    response=client.get(f'/api/evaluations/{id}/export-predictions?format=jsonl')
    assert len(response.text.strip().splitlines())==8


def test_metrics_match_sklearn():
    gold=[['A'],['B'],['A'],['C'],['B'],['A']];pred=[['A'],['A'],['C'],['C'],['B'],['B']]
    labels=['A','B','C','D'];result=score(gold,pred,labels,'single');y=[x[0] for x in gold];p=[x[0] for x in pred]
    assert result['summary']['accuracy']==accuracy_score(y,p)
    assert result['summary']['hamming_loss']==pytest.approx(hamming_loss(y,p))
    assert result['summary']['kappa']==pytest.approx(cohen_kappa_score(y,p,labels=labels))
    assert result['summary']['mcc']==pytest.approx(matthews_corrcoef(y,p))
    for avg in ('micro','macro','weighted'):
        expected=precision_recall_fscore_support(y,p,labels=labels,average=avg,zero_division=0)
        for metric,value in zip(('precision','recall','f1'),expected[:3]):
            assert result['summary'][metric+'_'+avg]==pytest.approx(value)
    for row in result['per_class']:
        yb=[int(v==row['label']) for v in y];pb=[int(v==row['label']) for v in p]
        assert row['mcc']==pytest.approx(matthews_corrcoef(yb,pb))
        if row['label']!='D':assert row['kappa']==pytest.approx(cohen_kappa_score(yb,pb))
        else:assert row['kappa'] is None


def test_multilabel_metrics_match_sklearn():
    gold=[['A','B'],[],['C'],['A'],['B','C']];pred=[['A'],[],['B','C'],['A'],['C']];labels=['A','B','C']
    result=score(gold,pred,labels,'multi')
    y=np.array([[int(l in x) for l in labels] for x in gold]);p=np.array([[int(l in x) for l in labels] for x in pred])
    assert result['summary']['accuracy']==accuracy_score(y,p)
    assert result['summary']['hamming_loss']==hamming_loss(y,p)
    assert result['summary']['jaccard_samples']==jaccard_score(y,p,average='samples',zero_division=0)
    assert 'kappa' not in result['summary']
    for avg in ('micro','macro','weighted','samples'):
        expected=precision_recall_fscore_support(y,p,average=avg,zero_division=0)
        for metric,value in zip(('precision','recall','f1'),expected[:3]):assert result['summary'][metric+'_'+avg]==pytest.approx(value)
    kappas=[cohen_kappa_score(y[:,i],p[:,i]) for i in range(3)]
    assert result['summary']['kappa_macro_ovr']==pytest.approx(np.mean(kappas))
    assert result['summary']['mcc_macro_ovr']==pytest.approx(np.mean([matthews_corrcoef(y[:,i],p[:,i]) for i in range(3)]))


def test_shared_subset_and_failure_coverage(client,monkeypatch):
    gold,task,profile,_=setup(client)
    import textlab.worker as worker
    original=worker.classify
    def fail_some(snapshot,text,http):
        result=original(snapshot,text,http)
        if text==('Beta' if snapshot['query']['temperature']==0 else 'Gamma'):
            result.update(status='failed',labels=[],error='Test failure')
        return result
    monkeypatch.setattr(worker,'classify',fail_some)
    id,_=evaluate(client,gold,task,profile)
    common=client.get(f'/api/evaluations/{id}/report?scope=common').json()
    valid=client.get(f'/api/evaluations/{id}/report?scope=valid').json()
    assert common['common_n']==2
    assert all(r['n']==2 and r['coverage']==.75 and r['accuracy_all']==.5 for r in common['runs'])
    assert all(r['n']==3 for r in valid['runs'])


def test_multilabel_registration_and_no_gold_leak(client,monkeypatch):
    gold,task,profile,_=setup(client,multi=True,content=b'document,body,annotation\n001,Alpha,A|B\n002,Beta,\n003,Gamma,C\n')
    import textlab.worker as worker
    original=worker.classify
    def capture(snapshot,text,http):
        assert text in ('Alpha','Beta','Gamma')
        assert 'annotation' not in snapshot and 'gold_labels' not in snapshot
        return original(snapshot,text,http)
    monkeypatch.setattr(worker,'classify',capture)
    id,state=evaluate(client,gold,task,profile)
    preview=client.get('/api/gold-sets/'+gold+'/preview').json()
    assert preview[0]['gold_labels']==['A','B'] and preview[1]['gold_labels']==[]
    assert client.get('/api/evaluations/'+id+'/report').json()['mode']=='multi'


def test_no_valid_results_are_not_zero(client,monkeypatch):
    gold,task,profile,_=setup(client)
    import textlab.worker as worker
    original=worker.classify
    def fail(snapshot,text,http):
        result=original(snapshot,text,http);result.update(status='failed',labels=[]);return result
    monkeypatch.setattr(worker,'classify',fail)
    id,_=evaluate(client,gold,task,profile)
    report=client.get('/api/evaluations/'+id+'/report').json()
    assert report['common_n']==0
    assert report['runs'][0]['summary']['accuracy'] is None
    assert report['runs'][0]['coverage']==0 and report['runs'][0]['accuracy_all']==0
    assert client.get(f'/api/evaluations/{id}/chart?kind=classes&metric=f1').status_code==200


@pytest.mark.parametrize('content',[
 b'doc_id,text,gold_label\n1,x,A\n1,y,B\n',
 b'doc_id,text,gold_label\n,x,A\n',
 b'doc_id,text,gold_label\n1,,A\n',
 b'doc_id,text,gold_label\n1,x,A||B\n',
 b'doc_id,text,gold_label\n1,x,A|A\n'])
def test_bad_gold_rejected_atomically(client,content):
    did=client.post('/api/datasets',content=content).json()['id'];tick()
    response=client.post('/api/gold-sets',json={'name':'bad','dataset_id':did,'mode':'multi'})
    assert response.status_code==422
    assert client.get('/api/gold-sets').json()==[]
    with connect() as db:assert db.execute('SELECT count(*) FROM gold_rows').fetchone()[0]==0


def test_unknown_gold_label_and_mode_rejected_before_jobs(client):
    gold,task,profile,_=setup(client)
    bad={**TASK,'categories':TASK['categories'][:2]}
    tid=client.post('/api/tasks',json=bad).json()['id']
    spec={'name':'bad','gold_id':gold,'task_id':tid,'variants':[{'name':'v','profile_id':profile,'query':{'model':'mock'}}]}
    assert client.post('/api/evaluations',json=spec).status_code==422
    assert client.get('/api/jobs').json()==[]
    spec['task_id']=client.post('/api/tasks',json={**TASK,'mode':'multi'}).json()['id']
    assert client.post('/api/evaluations',json=spec).status_code==422


def test_evidence_and_reasoning_all_attempts(monkeypatch):
    calls=[]
    def handle(request):
        body=json.loads(request.content);calls.append(body)
        quote='invented' if len(calls)==1 else 'evidence'
        raw=json.dumps({'labels':['A'],'evidence':[{'label':'A','quote':quote}]})
        return httpx.Response(200,json={'choices':[{'message':{'content':raw,'reasoning_content':'thinking '+str(len(calls))}}]})
    monkeypatch.setattr('textlab.llm.time.sleep',lambda _:None)
    snapshot={'task':{**TASK,'rationale':True},'query':{'model':'model','rationale':False,'evidence':True},'profile':{'name':'p','provider':'openai','base_url':'http://localhost'}}
    with httpx.Client(transport=httpx.MockTransport(handle)) as c:result=classify(snapshot,'Some evidence here',c)
    assert result['status']=='ok' and result['attempts']==2 and result['rationale'] is None
    assert result['evidence']==[{'label':'A','quote':'evidence','start':5,'end':13}]
    assert result['thinking']=='thinking 2'
    assert [x['thinking'] for x in result['attempt_outputs']]==['thinking 1','thinking 2']
    assert result['attempt_outputs'][0]['error']
    assert 'rationale' not in calls[0]['response_format']['json_schema']['schema']['properties']


@pytest.mark.parametrize('provider,field',[('ollama','thinking'),('openai','reasoning'),('openai','reasoning_content')])
def test_reasoning_provider_keys(provider,field):
    msg={'content':'{"labels":["A"]}',field:'server thinking'}
    body={'message':msg} if provider=='ollama' else {'choices':[{'message':msg}]}
    snapshot={'task':TASK,'query':{'model':'m'},'profile':{'name':'p','provider':provider,'base_url':'http://localhost'}}
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json=body))) as c:r=classify(snapshot,'a',c)
    assert r['status']=='ok' and r['thinking']=='server thinking'


def test_inline_thinking_and_empty_final_answer(monkeypatch):
    monkeypatch.setattr('textlab.llm.time.sleep',lambda _:None)
    snapshot={'task':TASK,'query':{'model':'m','retries':0},'profile':{'name':'p','provider':'openai','base_url':'http://localhost'}}
    for content,status in [('<think>server trace</think>{"labels":["A"]}','ok'),('<think>server trace</think>','failed')]:
        with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'choices':[{'message':{'content':content}}]}))) as c:r=classify(snapshot,'a',c)
        assert r['status']==status and r['thinking']=='server trace' and r['raw']==content


def test_migration_preserves_legacy_results(tmp_path,monkeypatch):
    monkeypatch.setenv('TEXTLAB_DATA',str(tmp_path))
    db=sqlite3.connect(tmp_path/'textlab.sqlite')
    db.executescript('''CREATE TABLE results(job_id TEXT,row_no INTEGER,labels TEXT,rationale TEXT,status TEXT,error TEXT,raw TEXT,attempts INTEGER,seconds REAL,prompt_tokens INTEGER,completion_tokens INTEGER,PRIMARY KEY(job_id,row_no));
    INSERT INTO results VALUES('legacy',1,'["A"]',NULL,'ok',NULL,'{}',1,1,0,0);''');db.close()
    init();init()
    with connect() as db:
        row=dict(db.execute('SELECT * FROM results').fetchone())
        assert row['labels']=='["A"]' and row['evidence']=='[]' and row['thinking'] is None
        assert db.execute('PRAGMA user_version').fetchone()[0]==5


def test_cancelled_evaluation_report_includes_unprocessed(client):
    gold,task,profile,_=setup(client)
    spec={'name':'cancel','gold_id':gold,'task_id':task,'variants':[{'name':'v','profile_id':profile,'query':{'model':'mock'}}]}
    id=client.post('/api/evaluations',json=spec).json()['id']
    assert client.post('/api/evaluations/'+id+'/cancel').status_code==200
    tick()
    report=client.get('/api/evaluations/'+id+'/report').json()
    assert report['runs'][0]['unprocessed_n']==4 and report['runs'][0]['n']==0
    rows=client.get('/api/evaluations/'+id+'/export-predictions?format=jsonl').text.strip().splitlines()
    assert len(rows)==4 and json.loads(rows[0])['status']=='not_processed'
