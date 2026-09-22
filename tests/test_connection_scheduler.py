"""Regression: independent servers, immutable evaluation snapshots and drain controls."""
import json
import threading
import time

from test_evaluation import client, setup
from cca_lab.db import connect
from cca_lab.worker import ConnectionScheduler, tick, endpoint_key


def create(client, gold, task, profile, model, seeds):
    response = client.post('/api/evaluations', json={
        'name': model, 'gold_id': gold, 'task_id': task,
        'variants': [{'name': model, 'profile_id': profile, 'seeds': seeds,
                      'query': {'model': model}}]})
    assert response.status_code == 201, response.text
    return response.json()


def test_evaluation_snapshot_isolation(client):
    gold, task, p1, _ = setup(client)
    p2 = client.post('/api/profiles', json={'name': 'Second server', 'provider': 'mock',
                                         'base_url': 'http://other:8000/v1'}).json()['id']
    first = create(client, gold, task, p1, 'gemma', [9721, 13, 7])
    before = client.get('/api/evaluations/' + first['id']).json()
    second = create(client, gold, task, p2, 'gpt-oss', [9721])
    # Even changing a live connection cannot rewrite an existing job's configuration.
    client.put('/api/profiles/' + p1, json={'name': 'Renamed', 'provider': 'mock',
                                          'base_url': 'http://changed:8000'})
    after = client.get('/api/evaluations/' + first['id']).json()
    assert before == after
    assert len(after['runs']) == 3
    assert all(r['model'] == 'gemma' and r['connection']['name'] == 'Mock' for r in after['runs'])
    other = client.get('/api/evaluations/' + second['id']).json()
    assert all(r['model'] == 'gpt-oss' and r['connection']['name'] == 'Second server' for r in other['runs'])


def test_servers_overlap_but_same_server_waits_and_controls_drain(client, monkeypatch):
    gold, task, p1, _ = setup(client)
    p2 = client.post('/api/profiles', json={'name': 'Second', 'provider': 'mock',
                                         'base_url': 'http://other:8000'}).json()['id']
    a = create(client, gold, task, p1, 'gemma', [9721, 13])
    b = create(client, gold, task, p2, 'gpt-oss', [9721])
    entered = {a['job_ids'][0]: threading.Event(), b['job_ids'][0]: threading.Event()}
    release = threading.Event()
    calls = []

    def blocked_window(job):
        calls.append(job['id'])
        entered[job['id']].set()
        assert release.wait(5)

    monkeypatch.setattr('cca_lab.worker.run_batch', blocked_window)
    scheduler = ConnectionScheduler()
    try:
        tick(scheduler)
        assert all(event.wait(3) for event in entered.values()), 'Both servers must start before either finishes'
        assert set(calls) == set(entered)
        tick(scheduler)
        assert len(calls) == 2, 'No duplicate dispatch or second job on a busy endpoint'
        client.post('/api/evaluations/' + a['id'] + '/pause')
        client.post('/api/evaluations/' + b['id'] + '/cancel')
        tick(scheduler)
        with connect() as db:
            assert db.execute('SELECT status FROM jobs WHERE id=?', (a['job_ids'][0],)).fetchone()[0] == 'pausing'
            assert db.execute('SELECT status FROM jobs WHERE id=?', (a['job_ids'][1],)).fetchone()[0] == 'paused'
            assert db.execute('SELECT status FROM jobs WHERE id=?', (b['job_ids'][0],)).fetchone()[0] == 'cancelling'
        release.set()
        for _, future in scheduler.active.values():
            future.result(timeout=5)
        tick(scheduler)
        with connect() as db:
            assert db.execute('SELECT status FROM jobs WHERE id=?', (a['job_ids'][0],)).fetchone()[0] == 'paused'
            assert db.execute('SELECT status FROM jobs WHERE id=?', (b['job_ids'][0],)).fetchone()[0] == 'cancelled'
            assert db.execute('SELECT COUNT(*) FROM jobs WHERE active_since IS NOT NULL').fetchone()[0] == 0
    finally:
        release.set()
        scheduler.close()


def test_connection_aliases_share_capacity():
    def job(url):
        return {'snapshot': json.dumps({'profile': {'base_url': url}})}
    assert endpoint_key(job('http://SERVER:80/v1')) == endpoint_key(job('http://server/api'))
    assert endpoint_key(job('http://server:8001')) != endpoint_key(job('http://server:8000'))
