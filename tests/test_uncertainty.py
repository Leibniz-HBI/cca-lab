from task_fixtures import task_spec
import io
import json
import math
import zipfile
import pytest
from fastapi.testclient import TestClient
from textlab.api import app
from textlab.db import connect, dumps
from textlab.llm import parse_result, output_schema, classify
from textlab.models import Task
from textlab.uncertainty import confidence_metrics, agreement_summary, group_confidence
from textlab.worker import tick
TASK = task_spec(**{'name': 'Stance', 'instructions': 'Code stance.', 'categories': [{'label': 'A', 'definition': 'Alpha'}, {'label': 'B', 'definition': 'Beta'}], 'confidence': True, 'alternatives': True})

def example():
    return {'candidate_interpretations': [{'labels': ['B'], 'justification': 'Plausible alternate reading.', 'supporting_quotes': ['Beta'], 'boundary_note': 'Speaker attribution is uncertain.'}, {'labels': ['A'], 'justification': 'Best fit.', 'supporting_quotes': ['Alpha'], 'boundary_note': 'Beta is a competing reading.'}], 'labels': ['A'], 'self_reported_confidence': 0.65}

def test_structured_alternatives_and_confidence_validation():
    task = Task(**TASK)
    obj = example()
    assert parse_result(dumps(obj), task, 'Alpha Beta') == {**obj, 'alternative_interpretations': obj['candidate_interpretations'][:1]}
    assert set(output_schema(task)['required']) == set(obj)
    for bad in [True, -0.01, 1.01, float('nan'), float('inf'), '0.5', None]:
        with pytest.raises(ValueError):
            parse_result(json.dumps({**obj, 'self_reported_confidence': bad}), task, 'Alpha Beta')
    for labels in [['A'], ['unknown'], ['B', 'B'], ['A', 'B'], []]:
        broken = example()
        broken['candidate_interpretations'][0]['labels'] = labels
        with pytest.raises(ValueError):
            parse_result(dumps(broken), task, 'Alpha Beta')
    with pytest.raises(ValueError):
        parse_result(dumps(obj), task, 'Alpha only')
    with pytest.raises(ValueError):
        parse_result(dumps(obj), Task(**task_spec(TASK, alternatives=False)), 'Alpha Beta')

def test_multilabel_alternatives_are_sets_not_additional_labels():
    task = Task(**task_spec(TASK, mode='multi'))
    obj = example()
    obj['labels'] = ['A', 'B']
    obj['candidate_interpretations'][1]['labels'] = ['A', 'B']
    obj['candidate_interpretations'][0]['labels'] = ['A']
    assert parse_result(dumps(obj), task, 'Alpha Beta')['alternative_interpretations'][0]['labels'] == ['A']
    obj['candidate_interpretations'][0]['labels'] = ['B', 'A']
    with pytest.raises(ValueError):
        parse_result(dumps(obj), task, 'Alpha Beta')

def test_confidence_metrics_ties_and_degenerate_cases():
    result = confidence_metrics([(0.9, 1), (0.9, 0), (0.1, 0), (0.1, 0)])
    assert result['brier'] == pytest.approx(0.21)
    assert result['ece'] == pytest.approx(0.25)
    assert len(result['risk']) == 2 and result['risk'][0] == {'threshold': 0.9, 'coverage': 0.5, 'risk': 0.5}
    assert result['error_auroc'] == pytest.approx(5 / 6)
    assert confidence_metrics([])['brier'] is None
    assert confidence_metrics([(1, 1)])['error_auroc'] is None
    c = group_confidence([{'status': 'completed', 'confidence': confidence_metrics([(0.5, 1)])}, {'status': 'completed', 'confidence': confidence_metrics([(0.5, 0)])}, {'status': 'cancelled', 'confidence': confidence_metrics([(0, 1)])}])
    assert c['bins'][5]['accuracy'] == 0.5 and c['bins'][5]['sd'] == pytest.approx(math.sqrt(0.5))

def test_agreement_excludes_fallback_and_retains_modal_ties():
    out = agreement_summary([{'labels': '["A"]', 'status': 'ok'}, {'labels': '["B"]', 'status': 'ok'}, {'labels': '["A"]', 'status': 'fallback'}], ['A', 'B'], 4)
    assert out['valid_runs'] == 2 and out['fallback_runs'] == 1 and (out['unprocessed_runs'] == 1)
    assert out['modal_vote_share'] == 0.5 and out['label_set_entropy_bits'] == 1
    assert sorted(out['modal_label_sets']) == [['A'], ['B']]
    assert agreement_summary([{'labels': '["A"]', 'status': 'ok'}], ['A', 'B'], 1)['modal_vote_share'] is None

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('TEXTLAB_DATA', str(tmp_path))
    with TestClient(app) as c:
        yield c

def setup(c):
    did = c.post('/api/datasets', content=b'doc_id,text,gold_label\n001,Alpha Beta,A\n002,Beta Alpha,B\n').json()['id']
    tick()
    tid = c.post('/api/tasks', json=TASK).json()['id']
    pid = c.post('/api/profiles', json={'name': 'Demo', 'provider': 'mock', 'base_url': 'http://localhost'}).json()['id']
    gid = c.post('/api/gold-sets', json={'name': 'Gold', 'dataset_id': did}).json()['id']
    return (did, tid, pid, gid)

def test_confidence_roundtrip_reports_exports_and_query_counts(client):
    did, tid, pid, gid = setup(client)
    e = client.post('/api/evaluations', json={'name': 'Confidence', 'task_id': tid, 'gold_id': gid, 'seeds': [11, 22], 'variants': [{'name': 'm1', 'profile_id': pid, 'query': {'model': 'm1', 'retries': 0}}, {'name': 'm2', 'profile_id': pid, 'query': {'model': 'm2', 'retries': 2}, 'seeds': [1, 2, 3]}]}).json()
    assert client.get('/api/evaluations/' + e['id']).json()['query_count'] == {'planned': 10, 'maximum_attempts': 22, 'runs': 5}
    assert client.get('/api/evaluations/' + e['id'] + '/agreement').status_code == 409
    for _ in range(30):
        tick()
    r = client.get('/api/evaluations/' + e['id'] + '/report').json()
    assert r['groups'][0]['confidence']['metrics']['brier']['mean'] == 0.25
    assert r['groups'][0]['confidence']['metrics']['n']['mean'] == 2
    for kind in ('risk', 'reliability'):
        image = client.get(f"/api/evaluations/{e['id']}/confidence-chart?kind={kind}")
        assert image.status_code == 200 and '<svg' in image.text
    agreement = client.get('/api/evaluations/' + e['id'] + '/agreement').json()
    assert len(agreement) == 4 and agreement[0]['modal_vote_share'] == 1
    raw = client.get('/api/jobs/' + e['job_ids'][0] + '/results').json()[0]
    assert raw['self_reported_confidence'] == 0.5 and raw['alternative_interpretations'] == []
    assert 'self_reported_confidence' in client.get('/api/evaluations/' + e['id'] + '/export-predictions').text
    bundle = zipfile.ZipFile(io.BytesIO(client.get('/api/evaluations/' + e['id'] + '/report?format=zip').content))
    assert {'confidence.json', 'confidence-risk.png', 'agreement.csv'} <= set(bundle.namelist())
    p = client.post('/api/predictions', json={'name': 'Pred', 'dataset_id': did, 'task_ids': [tid], 'profile_id': pid, 'text_column': 'text', 'seeds': [4, 5], 'query': {'model': 'm', 'retries': 1}}).json()
    for _ in range(20):
        tick()
    info = client.get('/api/predictions/' + p['id']).json()
    assert info['query_count'] == {'planned': 4, 'maximum_attempts': 8, 'runs': 2}
    assert info['artifact_status'] == 'ready'
    assert len(client.get('/api/predictions/' + p['id'] + '/download/agreement_jsonl').text.splitlines()) == 2
    import pyarrow.parquet as pq
    table = pq.read_table(io.BytesIO(client.get('/api/predictions/' + p['id'] + '/download/parquet').content))
    assert table['prediction.self_reported_confidence'].to_pylist() == [0.5] * 4
    assert client.get('/api/predictions/' + p['id'] + '/agreement?after=1').json()[0]['row_no'] == 2

def test_fallback_confidence_unavailable_and_alternative_retry(monkeypatch):
    import httpx
    task = task_spec(TASK, default_label='B')
    calls = []

    def reply(request):
        calls.append(request)
        invalid = example()
        invalid['candidate_interpretations'][0]['supporting_quotes'] = ['not in text']
        return httpx.Response(200, json={'choices': [{'message': {'content': dumps(invalid)}}]})
    snapshot = {'task': task, 'query': {'model': 'm', 'retries': 1}, 'profile': {'name': 'Server', 'provider': 'openai', 'base_url': 'http://localhost'}}
    monkeypatch.setattr('textlab.llm.time.sleep', lambda _: None)
    with httpx.Client(transport=httpx.MockTransport(reply)) as c:
        r = classify(snapshot, 'Alpha Beta', c)
    assert len(calls) == 2 and r['status'] == 'fallback' and (r['labels'] == ['B'])
    assert r.get('self_reported_confidence') is None and (not r.get('alternative_interpretations'))

def test_alternative_persistence_and_numeric_job_parquet(client, monkeypatch):
    import httpx
    import pyarrow.parquet as pq
    did, tid, pid, gid = setup(client)

    def classified(snapshot, text, unused):
        snapshot = {**snapshot, 'profile': {'name': 'Simulated API', 'provider': 'openai', 'base_url': 'http://localhost'}}

        def response(req):
            return httpx.Response(200, json={'choices': [{'message': {'content': dumps(example())}}]})
        with httpx.Client(transport=httpx.MockTransport(response)) as transport:
            return classify(snapshot, text, transport)
    monkeypatch.setattr('textlab.worker.classify', classified)
    jid = client.post('/api/jobs', json={'name': 'Roundtrip', 'dataset_id': did, 'task_id': tid, 'profile_id': pid, 'text_column': 'text', 'query': {'model': 'm'}}).json()['id']
    for _ in range(5):
        tick()
    rows = client.get('/api/jobs/' + jid + '/results').json()
    assert rows[0]['candidate_interpretations'] == example()['candidate_interpretations']
    assert rows[0]['alternative_interpretations'] == example()['candidate_interpretations'][:1]
    table = pq.read_table(io.BytesIO(client.get('/api/jobs/' + jid + '/export?format=parquet').content))
    assert table['classification.self_reported_confidence'].to_pylist() == [0.65, 0.65]
    assert json.loads(table['classification.candidate_interpretations'][0].as_py()) == example()['candidate_interpretations']
    assert json.loads(table['classification.alternative_interpretations'][0].as_py()) == example()['candidate_interpretations'][:1]

def test_agreement_deduplicates_same_seed_and_excludes_cancelled_runs(client):
    did, tid, pid, gid = setup(client)
    e = client.post('/api/evaluations', json={'name': 'Repeated seed', 'task_id': tid, 'gold_id': gid, 'variants': [{'name': str(i), 'profile_id': pid, 'query': {'model': 'm', 'seed': 11}} for i in range(3)]}).json()
    with connect() as db:
        db.execute("UPDATE jobs SET status='cancelled' WHERE id=?", (e['job_ids'][2],))
    for _ in range(20):
        tick()
    rows = client.get('/api/evaluations/' + e['id'] + '/agreement').json()
    assert rows[0]['duplicate_seed_runs'] == 1 and rows[0]['cancelled_runs'] == 1
    assert rows[0]['valid_runs'] == 1 and rows[0]['modal_vote_share'] is None
