from task_fixtures import task_spec
import csv
import io
import json
import math
import httpx
import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient
from cca_lab.api import app
from cca_lab.db import connect, init
from cca_lab.models import Task, NewEvaluation, parse_seeds
from cca_lab.repetitions import aggregate_runs
from cca_lab.worker import tick
TASK = task_spec(**{'name': 'Topic', 'instructions': 'Assign the topic.', 'categories': [{'label': 'A', 'definition': 'Alpha'}, {'label': 'B', 'definition': 'Beta'}]})

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('CCA_LAB_DATA', str(tmp_path))
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






def test_prediction_task_times_seed_product_and_exports(client):
    did, tid, pid, _ = setup(client)
    other = client.post('/api/tasks', json=task_spec(TASK, name='Other')).json()['id']
    response = client.post('/api/predictions', json={'name': 'Repeat prediction', 'dataset_id': did, 'task_ids': [tid, other], 'text_column': 'text', 'seeds': '1,2,3', 'variants': [{'name': 'Configuration', 'profile_id': pid, 'query': {'model': 'm'}}]})
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
