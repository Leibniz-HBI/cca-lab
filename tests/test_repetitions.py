from task_fixtures import legacy_jobs
from task_fixtures import task_spec
import csv
import io
import json
import math
import httpx
import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient
from textlab.api import app
from textlab.db import connect, init
from textlab.llm import classify
from textlab.models import Task, NewEvaluation, parse_seeds
from textlab.repetitions import aggregate_runs
from textlab.worker import tick
TASK = task_spec(**{'name': 'Topic', 'instructions': 'Assign the topic.', 'categories': [{'label': 'A', 'definition': 'Alpha'}, {'label': 'B', 'definition': 'Beta'}]})

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('TEXTLAB_DATA', str(tmp_path))
    with TestClient(app) as c:
        yield c

def setup(c, task=None):
    did = c.post('/api/datasets', content=b'doc_id,text,gold_label\n001,Alpha,A\n002,Beta,B\n').json()['id']
    tick()
    tid = c.post('/api/tasks', json=task or TASK).json()['id']
    pid = c.post('/api/profiles', json={'name': 'Demo', 'provider': 'mock', 'base_url': 'http://localhost'}).json()['id']
    gid = c.post('/api/gold-sets', json={'name': 'Gold', 'dataset_id': did}).json()['id']
    return (did, tid, pid, gid)

def drain(c, path):
    for _ in range(30):
        tick()
        r = c.get(path).json()
        if r.get('report_ready') or r.get('artifact_status') == 'ready':
            return r
        assert not r.get('report_error') and r.get('artifact_status') != 'failed', r
    raise AssertionError('Did not finish')

def test_fallback_after_attempts_preserves_errors_and_thinking(monkeypatch):
    monkeypatch.setattr('textlab.llm.time.sleep', lambda _: None)
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={'choices': [{'message': {'content': '{"labels":["WRONG"]}', 'reasoning_content': 'trace'}}]})
    snapshot = {'task': task_spec(TASK, default_label='B'), 'profile': {'name': 'P', 'provider': 'openai', 'base_url': 'http://localhost'}, 'query': {'model': 'm', 'seed': 23, 'retries': 2}}
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        r = classify(snapshot, 'Alpha', http)
        assert r['status'] == 'fallback' and r['labels'] == ['B'] and (r['attempts'] == 3)
        assert r['error'] and r['raw'] and (r['thinking'] == 'trace') and all((a['error'] for a in r['attempt_outputs']))
        assert all((c['seed'] == 23 for c in calls))
        snapshot['task']['execution_defaults']['default_label'] = None
        assert classify(snapshot, 'Alpha', http)['status'] == 'failed'
        snapshot['task']['execution_defaults']['default_label'] = 'B'
        assert classify(snapshot, '', http)['labels'] == []
        snapshot['query']['max_text_chars'] = 1
        assert classify(snapshot, 'Alpha', http)['labels'] == []
    with pytest.raises(ValueError):
        Task(**task_spec(TASK, default_label='UNKNOWN'))
    assert Task(**task_spec(TASK, default_label='B', mode='multi')).default_label == 'B'

def test_saved_snapshot_live_error_log_pagination_and_recovered_attempts(client, monkeypatch):
    did, tid, pid, _ = setup(client)
    job = client.post('/api/jobs', json={'name': 'Errors', 'dataset_id': did, 'task_id': tid, 'profile_id': pid, 'text_column': 'text', 'query': {'model': 'm', 'concurrency': 1}}).json()['id']
    import textlab.worker as w
    original = w.classify

    def fake(snapshot, text, http):
        r = original(snapshot, text, http)
        r['attempt_outputs'] = [{'attempt': 1, 'error': 'Invalid label', 'content': 'bad', 'thinking': 'trace'}]
        if text == 'Alpha':
            r.update(status='fallback', labels=['B'], error='Invalid label')
        else:
            r.update(attempts=2)
            r['attempt_outputs'].append({'attempt': 2, 'error': None, 'content': '{"labels":["A"]}'})
        return r
    monkeypatch.setattr(w, 'classify', fake)
    legacy_jobs(default_label="B"); tick()
    page = client.get(f'/api/jobs/{job}/errors?limit=1').json()
    assert page['status'] == 'running' and page['total'] == 1
    assert page['rows'][0]['fallback_used'] and page['rows'][0]['source']['doc_id'] == '001'
    for _ in range(4):
        legacy_jobs(default_label="B"); tick()
    page = client.get(f'/api/jobs/{job}/errors?after=1&limit=1').json()
    assert page['next_after'] == 2 and page['rows'][0]['status'] == 'ok'
    assert client.get(f'/api/jobs/{job}/errors?include_recovered=false').json()['total'] == 1
    rows = client.get(f'/api/jobs/{job}/errors?format=jsonl').text.splitlines()
    assert len(rows) == 2 and json.loads(rows[1])['attempt_outputs'][0]['error'] == 'Invalid label'
    j = client.get('/api/jobs/' + job).json()
    assert j['failed'] == 1 and j['fallback_count'] == 1
    assert client.get('/api/jobs/missing/errors').status_code == 404
    parquet = pq.read_table(io.BytesIO(client.get(f'/api/jobs/{job}/export?format=parquet').content))
    assert parquet['classification.fallback_used'].to_pylist() == [True, False]


def test_saved_snapshot_seeded_evaluation_means_sample_sd_and_fallback_scoring(client, monkeypatch):
    _, tid, pid, gid = setup(client, task_spec(TASK, default_label='B'))
    import textlab.worker as w
    original = w.classify

    def fake(snapshot, text, http):
        r = original(snapshot, text, http)
        if snapshot['query']['seed'] == 11:
            r['labels'] = ['A' if text == 'Alpha' else 'B']
        else:
            r.update(status='fallback', labels=['B'], error='Invalid output')
        return r
    monkeypatch.setattr(w, 'classify', fake)
    body = {'name': 'Repeated', 'task_id': tid, 'gold_id': gid, 'seeds': '11,22', 'variants': [{'name': 'Config', 'profile_id': pid, 'query': {'model': 'm'}}]}
    response = client.post('/api/evaluations', json=body)
    assert response.status_code == 201, response.text
    id = response.json()['id']
    legacy_jobs(default_label='B')
    state = drain(client, '/api/evaluations/' + id)
    assert len(state['runs']) == 2 and {r['query']['seed'] for r in state['runs']} == {11, 22}
    report = client.get('/api/evaluations/' + id + '/report').json()
    group = report['groups'][0]
    assert len(report['groups']) == 1 and group['repeat_n'] == 2
    assert group['summary']['accuracy'] == 0.75
    assert group['std']['summary']['accuracy'] == pytest.approx(math.sqrt(0.125))
    assert group['sample_n']['summary']['accuracy'] == 2
    assert group['fallback_n'] == 1 and group['coverage'] == 0.5 and (group['output_coverage'] == 1)
    assert group['per_class'][0]['std']['f1'] is not None
    rows = list(csv.DictReader(io.StringIO(client.get(f'/api/evaluations/{id}/report?format=csv').content.decode('utf-8-sig'))))
    assert len(rows) == 1 and float(rows[0]['accuracy']) == 0.75 and ('accuracy_sd' in rows[0])
    for kind in ('overview', 'classes'):
        chart = client.get(f"/api/evaluations/{id}/chart?kind={kind}&metric={('f1' if kind == 'classes' else 'f1_macro')}")
        assert chart.status_code == 200 and 'sample SD' in chart.text
    predicted = [json.loads(s) for s in client.get(f'/api/evaluations/{id}/export-predictions?format=jsonl').text.splitlines()]
    assert len(predicted) == 4 and predicted[-1]['predicted_labels'] == ['B'] and predicted[-1]['fallback_used']


def test_prediction_task_times_seed_product_and_exports(client):
    did, tid, pid, _ = setup(client)
    other = client.post('/api/tasks', json=task_spec(TASK, name='Other')).json()['id']
    response = client.post('/api/predictions', json={'name': 'Repeat prediction', 'dataset_id': did, 'task_ids': [tid, other], 'profile_id': pid, 'text_column': 'text', 'seeds': '1,2,3', 'query': {'model': 'm'}})
    assert response.status_code == 201, response.text
    id = response.json()['id']
    p = drain(client, '/api/predictions/' + id)
    assert len(p['runs']) == 6 and len(p['groups']) == 2 and all((g['repeat_n'] == 3 for g in p['groups']))
    rows = client.get(f'/api/predictions/{id}/download/json').json()
    assert len(rows) == 12 and {r['seed'] for r in rows} == {1, 2, 3}
    assert len({(r['task_id'], r['seed'], r['row_no']) for r in rows}) == 12
    table = pq.read_table(io.BytesIO(client.get(f'/api/predictions/{id}/download/parquet').content))
    assert table.num_rows == 12 and set(table['prediction.seed'].to_pylist()) == {1, 2, 3}
    manifest = client.get(f'/api/predictions/{id}/download/manifest').json()
    assert len(manifest['groups']) == 2

def test_cancelled_seed_does_not_empty_common_scope(client):
    _, tid, pid, gid = setup(client)
    response = client.post('/api/evaluations', json={'name': 'Cancel one', 'task_id': tid, 'gold_id': gid, 'seeds': [1, 2], 'variants': [{'name': 'C', 'profile_id': pid, 'query': {'model': 'm'}}]}).json()
    client.post('/api/jobs/' + response['job_ids'][1] + '/cancel')
    drain(client, '/api/evaluations/' + response['id'])
    report = client.get('/api/evaluations/' + response['id'] + '/report').json()
    assert report['common_n'] == 2
    g = report['groups'][0]
    assert g['repeat_n'] == 1 and g['excluded_runs'] == 1
    assert g['summary']['accuracy'] == 0.5 and g['std']['summary']['accuracy'] is None

@pytest.mark.parametrize('seeds', ['1,,2', '1,one', [], [True], [1.5], [1, 1], list(range(101))])
def test_invalid_seed_lists(seeds):
    with pytest.raises(ValueError):
        parse_seeds(seeds)

def test_grouping_separates_other_parameters_and_counts_defined_values():

    def run(seed, temp, value, status='completed'):
        return {'job_id': str(seed) + str(temp), 'variant': 'Config', 'status': status, 'snapshot': {'task': TASK, 'query': {'model': 'm', 'seed': seed, 'temperature': temp}}, 'summary': {'kappa': value}}
    groups = aggregate_runs([run(1, 0, 0.2), run(2, 0, None), run(3, 0, 0.8), run(1, 1, 0.9), run(4, 0, 1, 'cancelled')])
    assert len(groups) == 2 and groups[0]['summary']['kappa'] == 0.5
    assert groups[0]['sample_n']['summary']['kappa'] == 2 and groups[0]['repeat_n'] == 3
    assert groups[0]['std']['summary']['kappa'] == pytest.approx(math.sqrt(0.18))

def test_seed_run_limit_rejected_before_enqueuing(client):
    did, tid, pid, gid = setup(client)
    payload = {'name': 'Too many', 'gold_id': gid, 'task_id': tid, 'seeds': list(range(100)), 'variants': [{'name': str(i), 'profile_id': pid, 'query': {'model': 'm'}} for i in range(6)]}
    assert client.post('/api/evaluations', json=payload).status_code == 422
    assert client.get('/api/jobs').json() == []
