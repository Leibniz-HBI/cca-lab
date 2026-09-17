import copy
import json
import pytest
from fastapi.testclient import TestClient
from textlab.api import app
from textlab.cca import SCHEMA, validate_codebook, from_codebook, to_codebook
from textlab.llm import messages
from textlab.models import Query, Task


def codebook():
    return {'$schema':SCHEMA['$id'],'id':'sentiment-study','version':'1.2.3','title':'Sentiment','description':'Evaluative tone',
      'language':'en','authors':['Research team'],'maintainers':['Editor'],'created_at':'2026-09-17','modified_at':'2026-09-17',
      'references':[{'citation':'Example methods reference','doi':'10.1234/example'}],
      'task':{'instructions':'Assign tone.','unit_of_analysis':'sentence','classification_mode':'single_label','context':'Use the preceding sentence to resolve irony.',
      'categories':[{'id':'101','label':'Positive','definition':'Favorable tone','inclusion_criteria':['Explicit praise'],'exclusion_criteria':['Irony'],'coding_notes':'Check attribution.','aliases':['pos']},{'id':'102','label':'Negative','definition':'Unfavorable tone'}]},
      'examples':[{'text':'Wonderful.','labels':['101'],'context':'The speaker welcomed the result.','explanation':'Expresses approval.'}]}


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('TEXTLAB_DATA',str(tmp_path))
    with TestClient(app) as c:yield c


def test_roundtrip_and_execution_semantics(client):
    doc=codebook();response=client.post('/api/tasks/import-cca',json=doc)
    assert response.status_code==201,response.text
    id=response.json()['id'];task=client.get('/api/tasks').json()[0]['spec']
    assert task['categories'][0]['label']=='101' and task['categories'][0]['display_label']=='Positive'
    prompt=messages(Task(**task),Query(model='mock'),'Wonderful.')
    for value in ['sentence','Explicit praise','Irony','Check attribution.','Positive','Use the preceding sentence']:
        assert value in prompt[0]['content']
    assert json.loads(prompt[1]['content'])['context']=='The speaker welcomed the result.'
    assert json.loads(prompt[2]['content'])['labels']==['101']
    assert client.get('/api/tasks/'+id+'/export-cca').json()==doc
    task['categories'][0]['definition']='Updated operational definition'
    task['categories'][0]['inclusion_criteria']=['Updated criterion']
    task['name']='Edited sentiment'
    assert client.put('/api/tasks/'+id+'?revision=1',json=task).status_code==200
    exported=client.get('/api/tasks/'+id+'/export-cca').json()
    assert exported['task']['categories'][0]['definition']=='Updated operational definition'
    assert exported['task']['categories'][0]['inclusion_criteria']==['Updated criterion']
    assert exported['authors']==doc['authors'] and exported['version']=='1.2.3'
    assert exported['title']=='Edited sentiment'
    validate_codebook(exported)


@pytest.mark.parametrize('mutation',[
    lambda d:d['task']['categories'][1].update(id='101'),
    lambda d:d['examples'][0].update(labels=['Positive']),
    lambda d:d['examples'][0].update(labels=['101','102']),
    lambda d:d.update(created_at='2026-02-30'),
    lambda d:d.update(version='1.2'),
    lambda d:d.update(unknown=True),
    lambda d:d['task']['categories'][0].update(inclusion_criteria=[]),
])
def test_reject_invalid_without_partial_tasks(client,mutation):
    d=codebook();mutation(d)
    assert client.post('/api/tasks/import-cca',json=d).status_code==422
    assert client.get('/api/tasks').json()==[]


def test_multilabel_single_category_and_empty_policy(client):
    d=codebook();d['task']['classification_mode']='multi_label';d['examples'][0]['labels']=['101','102']
    task=from_codebook(d);assert task.mode=='multi'
    assert to_codebook(task,'local',1)==d
    task.allow_empty=True
    with pytest.raises(ValueError,match='empty label'):to_codebook(task,'local',1)
    d=codebook();d['task']['categories']=d['task']['categories'][:1]
    assert client.post('/api/tasks/import-cca',json=d).status_code==201


def test_native_export_and_import(client):
    t=Task(name='Native',instructions='Classify.',categories=[{'label':'A','definition':'Alpha','examples':['a']},{'label':'B','definition':'Beta'}])
    id=client.post('/api/tasks',json=t.model_dump()).json()['id']
    out=client.get('/api/tasks/'+id+'/export-cca')
    assert out.status_code==200
    doc=out.json();validate_codebook(doc)
    assert doc['description']=='Classify.' and doc['examples'][0]=={'text':'a','labels':['A']}
    assert 'Ambiguity rule:' in doc['task']['instructions']
    assert client.post('/api/tasks/import-cca',json=doc).status_code==201
    assert client.get('/api/tasks/'+id+'/export-cca').json()['id']==doc['id']


def test_bom_duplicate_keys_invalid_json_and_upload_limit(client):
    assert client.post('/api/tasks/import-cca',content=b'\xef\xbb\xbf'+json.dumps(codebook()).encode()).status_code==201
    before=len(client.get('/api/tasks').json())
    for content in [b'{"id":"a","id":"b"}',b'{broken',b'null',b'\xff']:
        assert client.post('/api/tasks/import-cca',content=content).status_code==422
    assert client.post('/api/tasks/import-cca',content=b' '* (5*1024*1024+1)).status_code==413
    assert len(client.get('/api/tasks').json())==before


def test_import_diagnostics_correlate_without_payload(client, caplog):
    import logging
    caplog.set_level(logging.DEBUG, logger="textlab")
    doc = codebook()
    doc["description"] = "PRIVATE_CODEBOOK_CONTENT"
    response = client.post("/api/tasks/import-cca", json=doc)
    request_id = response.headers["X-Request-ID"]
    assert response.status_code == 201
    assert "cca_import_completed request_id=" + request_id in caplog.text
    assert response.json()["id"] in caplog.text
    failed = client.post("/api/tasks/import-cca", json={"secret": "PRIVATE_BAD_CONTENT"})
    assert failed.status_code == 422
    assert "cca_import_rejected request_id=" + failed.headers["X-Request-ID"] in caplog.text
    assert "PRIVATE_CODEBOOK_CONTENT" not in caplog.text
    assert "PRIVATE_BAD_CONTENT" not in caplog.text
