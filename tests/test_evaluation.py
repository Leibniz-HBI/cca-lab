from task_fixtures import task_spec
import csv
import io
import json
import sqlite3
import zipfile
import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, cohen_kappa_score, matthews_corrcoef, hamming_loss, jaccard_score
from cca_lab.api import app
from cca_lab.db import connect, init
from cca_lab.evaluation import score
from cca_lab.llm import parse_result, output_schema
from cca_lab.models import Task, GoldSet
from cca_lab.worker import tick
TASK = task_spec(**{'name': 'Topic', 'instructions': 'Select labels from the text.', 'categories': [{'label': 'A', 'definition': 'A'}, {'label': 'B', 'definition': 'B'}, {'label': 'C', 'definition': 'C'}]})

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('CCA_LAB_DATA', str(tmp_path))
    with TestClient(app) as c:
        yield c

def setup(client, multi=False, content=None):
    content = content or b'document,body,annotation\n001,Alpha,A\n002,Beta,B\n003,Gamma,C\n004,Delta,A\n'
    did = client.post('/api/datasets', content=content).json()['id']
    tick()
    r = client.post('/api/gold-sets', json={'name': 'Gold', 'dataset_id': did, 'doc_id_column': 'document', 'text_column': 'body', 'gold_column': 'annotation', 'mode': 'multi' if multi else 'single', 'separator': '|', 'allow_empty': multi})
    assert r.status_code == 201, r.text
    gold = r.json()['id']
    task = client.post('/api/tasks', json=task_spec(TASK, mode='multi' if multi else 'single')).json()['id']
    profile = client.post('/api/profiles', json={'name': 'Mock', 'provider': 'mock', 'base_url': 'http://localhost'}).json()['id']
    return (gold, task, profile, did)

def evaluate(client, gold, task, profile, variants=None):
    variants = variants or [{'name': 'T=0', 'profile_id': profile, 'query': {'model': 'mock', 'temperature': 0, 'rationale': True, 'evidence': True}}, {'name': 'T=.5', 'profile_id': profile, 'query': {'model': 'mock', 'temperature': 0.5}}]
    response = client.post('/api/evaluations', json={'name': 'Comparison', 'gold_id': gold, 'task_id': task, 'variants': variants})
    assert response.status_code == 201, response.text
    id = response.json()['id']
    for _ in range(30):
        tick()
        state = client.get('/api/evaluations/' + id).json()
        if state['report_ready']:
            return (id, state)
        assert not state['report_error'], state
    raise AssertionError('No report')

def test_evaluation_pipeline_reports_and_predictions(client):
    gold, task, profile, _ = setup(client)
    id, state = evaluate(client, gold, task, profile)
    assert state['status'] == 'completed' and len(state['runs']) == 2
    report = client.get('/api/evaluations/' + id + '/report').json()
    assert report['common_n'] == 4
    for r in report['runs']:
        assert r['summary']['accuracy'] == 0.5
        assert r['summary']['f1_macro'] == pytest.approx(2 / 3 / 3)
        assert r['coverage'] == 1 and r['accuracy_all'] == 0.5
    rows = client.get(f"/api/evaluations/{id}/predictions?job_id={state['runs'][0]['id']}").json()
    assert rows[0]['doc_id'] == '001' and rows[0]['gold_labels'] == ['A']
    assert rows[0]['evidence'] == [{'label': 'A', 'quote': 'Alpha', 'start': 0, 'end': 5}]
    assert rows[0]['rationale']
    assert rows[0]['predicted_labels'] == ['A']
    for format in ('csv', 'class_csv', 'html', 'json', 'zip'):
        response = client.get(f'/api/evaluations/{id}/report?format={format}')
        assert response.status_code == 200, response.text[:300]
        if format == 'zip':
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                assert {'report.html', 'report.json', 'metrics.csv', 'per_class.csv', 'predictions.csv', 'overview.png', 'classes.svg', 'confusion-01.svg'} <= set(z.namelist())
                assert z.testzip() is None
                assert len(list(csv.DictReader(io.StringIO(z.read('predictions.csv').decode('utf-8-sig'))))) == 8
    assert client.get(f'/api/evaluations/{id}/chart?kind=confusion').status_code == 200
    assert client.get(f'/api/evaluations/{id}/chart?metric=bad').status_code == 422
    response = client.get(f'/api/evaluations/{id}/export-predictions?format=jsonl')
    assert len(response.text.strip().splitlines()) == 8

def test_metrics_match_sklearn():
    gold = [['A'], ['B'], ['A'], ['C'], ['B'], ['A']]
    pred = [['A'], ['A'], ['C'], ['C'], ['B'], ['B']]
    labels = ['A', 'B', 'C', 'D']
    result = score(gold, pred, labels, 'single')
    y = [x[0] for x in gold]
    p = [x[0] for x in pred]
    assert result['summary']['accuracy'] == accuracy_score(y, p)
    assert result['summary']['hamming_loss'] == pytest.approx(hamming_loss(y, p))
    assert result['summary']['kappa'] == pytest.approx(cohen_kappa_score(y, p, labels=labels))
    assert result['summary']['mcc'] == pytest.approx(matthews_corrcoef(y, p))
    for avg in ('micro', 'macro', 'weighted'):
        expected = precision_recall_fscore_support(y, p, labels=labels, average=avg, zero_division=0)
        for metric, value in zip(('precision', 'recall', 'f1'), expected[:3]):
            assert result['summary'][metric + '_' + avg] == pytest.approx(value)
    for row in result['per_class']:
        yb = [int(v == row['label']) for v in y]
        pb = [int(v == row['label']) for v in p]
        assert row['mcc'] == pytest.approx(matthews_corrcoef(yb, pb))
        if row['label'] != 'D':
            assert row['kappa'] == pytest.approx(cohen_kappa_score(yb, pb))
        else:
            assert row['kappa'] is None

def test_multilabel_metrics_match_sklearn():
    gold = [['A', 'B'], [], ['C'], ['A'], ['B', 'C']]
    pred = [['A'], [], ['B', 'C'], ['A'], ['C']]
    labels = ['A', 'B', 'C']
    result = score(gold, pred, labels, 'multi')
    y = np.array([[int(l in x) for l in labels] for x in gold])
    p = np.array([[int(l in x) for l in labels] for x in pred])
    assert result['summary']['accuracy'] == accuracy_score(y, p)
    assert result['summary']['hamming_loss'] == hamming_loss(y, p)
    assert result['summary']['jaccard_samples'] == jaccard_score(y, p, average='samples', zero_division=0)
    assert 'kappa' not in result['summary']
    for avg in ('micro', 'macro', 'weighted', 'samples'):
        expected = precision_recall_fscore_support(y, p, average=avg, zero_division=0)
        for metric, value in zip(('precision', 'recall', 'f1'), expected[:3]):
            assert result['summary'][metric + '_' + avg] == pytest.approx(value)
    kappas = [cohen_kappa_score(y[:, i], p[:, i]) for i in range(3)]
    assert result['summary']['kappa_macro_ovr'] == pytest.approx(np.mean(kappas))
    assert result['summary']['mcc_macro_ovr'] == pytest.approx(np.mean([matthews_corrcoef(y[:, i], p[:, i]) for i in range(3)]))



def test_multilabel_registration_and_no_gold_leak(client, monkeypatch):
    gold, task, profile, _ = setup(client, multi=True, content=b'document,body,annotation\n001,Alpha,A|B\n002,Beta,B\n003,Gamma,C\n')
    import cca_lab.executor as executor
    original = executor.perform
    seen=[]

    def capture(profile, query, task, items, path, body, http):
        seen.extend(items)
        assert all(set(item)=={'id','text'} for item in items)
        assert all(item['text'] in ('Alpha','Beta','Gamma') for item in items)
        return original(profile,query,task,items,path,body,http)
    monkeypatch.setattr(executor, 'perform', capture)
    id, state = evaluate(client, gold, task, profile)
    assert len(seen)==6
    preview = client.get('/api/gold-sets/' + gold + '/preview').json()
    assert preview[0]['gold_labels'] == ['A', 'B'] and preview[1]['gold_labels'] == ['B']
    assert client.get('/api/evaluations/' + id + '/report').json()['mode'] == 'multi'



@pytest.mark.parametrize('content', [b'doc_id,text,gold_label\n1,x,A\n1,y,B\n', b'doc_id,text,gold_label\n,x,A\n', b'doc_id,text,gold_label\n1,,A\n', b'doc_id,text,gold_label\n1,x,A||B\n', b'doc_id,text,gold_label\n1,x,A|A\n'])
def test_bad_gold_rejected_atomically(client, content):
    did = client.post('/api/datasets', content=content).json()['id']
    tick()
    response = client.post('/api/gold-sets', json={'name': 'bad', 'dataset_id': did, 'mode': 'multi'})
    assert response.status_code == 422
    assert client.get('/api/gold-sets').json() == []
    with connect() as db:
        assert db.execute('SELECT count(*) FROM gold_rows').fetchone()[0] == 0

def test_unknown_gold_label_and_mode_rejected_before_jobs(client):
    gold, task, profile, _ = setup(client)
    bad = task_spec(TASK, categories=TASK['codebook']['task']['categories'][:2])
    tid = client.post('/api/tasks', json=bad).json()['id']
    spec = {'name': 'bad', 'gold_id': gold, 'task_id': tid, 'variants': [{'name': 'v', 'profile_id': profile, 'query': {'model': 'mock'}}]}
    assert client.post('/api/evaluations', json=spec).status_code == 422
    assert client.get('/api/jobs').json() == []
    spec['task_id'] = client.post('/api/tasks', json=task_spec(TASK, mode='multi')).json()['id']
    assert client.post('/api/evaluations', json=spec).status_code == 422




def test_cancelled_evaluation_report_includes_unprocessed(client):
    gold, task, profile, _ = setup(client)
    spec = {'name': 'cancel', 'gold_id': gold, 'task_id': task, 'variants': [{'name': 'v', 'profile_id': profile, 'query': {'model': 'mock'}}]}
    id = client.post('/api/evaluations', json=spec).json()['id']
    assert client.post('/api/evaluations/' + id + '/cancel').status_code == 200
    tick()
    report = client.get('/api/evaluations/' + id + '/report').json()
    assert report['runs'][0]['unprocessed_n'] == 4 and report['runs'][0]['n'] == 0
    rows = client.get('/api/evaluations/' + id + '/export-predictions?format=jsonl').text.strip().splitlines()
    assert len(rows) == 4 and json.loads(rows[0])['status'] == 'not_processed'
