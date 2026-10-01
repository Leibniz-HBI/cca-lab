from task_fixtures import runtime_task
from task_fixtures import task_spec
import csv
import io
import json
import threading
import time
import httpx
import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient
from cca_lab.api import app
from cca_lab.db import connect, init
from cca_lab.llm import parse_result
from cca_lab.models import Task
from cca_lab.worker import tick, run_batch, save_result
TASK = task_spec(**dict(name='Stance', instructions='Bestimme die Position.', categories=[dict(label='FOR', definition='Zustimmung', examples=['Ja!']), dict(label='AGAINST', definition='Ablehnung')]))

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('CCA_LAB_DATA', str(tmp_path))
    with TestClient(app) as c:
        yield c

def setup_job(client, content=b'id,text\n1,Ja\n2,Nein\n3,\n', **query):
    task = client.post('/api/tasks', json=TASK).json()['id']
    profile = client.post('/api/profiles', json=dict(name='Demo', provider='mock', base_url='http://localhost')).json()['id']
    dataset = client.post('/api/datasets?filename=test.csv', content=content).json()['id']
    tick()
    response = client.post('/api/jobs', json=dict(name='Test', task_id=task, profile_id=profile, dataset_id=dataset, text_column='text', query=dict(model='mock-classifier', **query)))
    assert response.status_code == 201, response.text
    return (response.json()['id'], task, dataset)

def finish(client, id):
    for _ in range(20):
        tick()
        job = client.get('/api/jobs/' + id).json()
        if job['status'].startswith('completed'):
            return job
    raise AssertionError('Did not complete')

def test_end_to_end_exports_snapshot(client):
    id, task, dataset = setup_job(client)
    updated = task_spec(TASK, name='Changed')
    assert client.put('/api/tasks/' + task + '?revision=1', json=updated).status_code == 200
    assert client.put('/api/tasks/' + task + '?revision=1', json=updated).status_code == 409
    job = finish(client, id)
    assert (job['done'], job['failed'], job['status']) == (3, 1, 'completed_with_errors')
    assert job['snapshot']['task']['codebook']['title'] == 'Stance'
    assert job['metrics']['requests'] == 2
    rows = client.get('/api/jobs/' + id + '/results').json()
    assert rows[0]['source'] == {'id': '1', 'text': 'Ja'}
    csv_response = client.get('/api/jobs/' + id + '/export?format=csv')
    csv_rows = list(csv.DictReader(io.StringIO(csv_response.content.decode('utf-8-sig'))))
    assert len(csv_rows) == 3 and csv_rows[0]['classification.labels'] == '["FOR"]'
    assert len(client.get('/api/jobs/' + id + '/export?format=jsonl').text.strip().splitlines()) == 3
    parquet = client.get('/api/jobs/' + id + '/export?format=parquet')
    assert pq.read_table(io.BytesIO(parquet.content)).num_rows == 3

def test_resume_and_partial_window_recovery(client):
    id, _, _ = setup_job(client, content=b'id,text\n1,yes\n2,no\n3,yes\n', concurrency=2)
    assert client.post('/api/jobs/' + id + '/pause').status_code == 200
    tick()
    assert client.get('/api/jobs/' + id).json()['status'] == 'paused'
    assert client.post('/api/jobs/' + id + '/resume').status_code == 200
    result = dict(labels=['FOR'], rationale=None, status='ok', error=None, raw='{"labels":["FOR"]}', attempts=1, seconds=0.1, prompt_tokens=0, completion_tokens=0)
    save_result(id, 1, result)
    save_result(id, 1, result)
    job = finish(client, id)
    assert job['done'] == 3 and job['metrics']['requests'] == 2
    assert len(client.get('/api/jobs/' + id + '/results').json()) == 3



def test_invalid_csv_and_limits(client, monkeypatch):
    client.post('/api/datasets', content=b'text,text\na,b\n')
    tick()
    assert client.get('/api/datasets').json()[0]['status'] == 'failed'
    monkeypatch.setenv('CCA_LAB_MAX_UPLOAD_BYTES', '5')
    assert client.post('/api/datasets', content=b'123456').status_code == 413

@pytest.mark.parametrize('raw', ['{"labels":["UNKNOWN"]}', '{"labels":["FOR","AGAINST"]}', '{"labels":[]}', '{"labels":["FOR"],"extra":1}', '```json\n{"labels":["FOR"]}\n```'])
def test_output_rejection(raw):
    with pytest.raises(ValueError):
        parse_result(raw, Task(**TASK))

def test_multi_label():
    task = runtime_task(TASK, mode='multi', rationale=True)
    assert parse_result('{"labels":[],"rationale":"No evidence"}', task)["labels"] == []
    assert parse_result('{"labels":["FOR","AGAINST"],"rationale":"Both"}', task)['labels'] == ['FOR', 'AGAINST']
    assert parse_result('{"labels":["FOR","FOR"],"rationale":""}', task)["labels"] == ["FOR"]


