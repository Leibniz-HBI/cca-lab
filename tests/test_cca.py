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
    assert task['codebook']==doc and set(task)=={'codebook','execution_defaults'}
    prompt=messages(Task(**task),Query(model='mock'),'Wonderful.')
    for value in ['sentence','Explicit praise','Irony','Check attribution.','Positive','Use the preceding sentence']:
        assert value in prompt[0]['content']
    assert 'The speaker welcomed the result.' in prompt[0]['content']
    assert '"101"' in prompt[0]['content']
    assert client.get('/api/tasks/'+id+'/export-cca').json()==doc
    task['codebook']['task']['categories'][0]['definition']='Updated operational definition'
    task['codebook']['task']['categories'][0]['inclusion_criteria']=['Updated criterion']
    task['codebook']['title']='Edited sentiment'
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
    assert to_codebook(task)==d
    from textlab.models import validate_labels
    validate_labels([],task)
    d=codebook();d['task']['categories']=d['task']['categories'][:1]
    assert client.post('/api/tasks/import-cca',json=d).status_code==201


def test_native_export_and_import(client):
    t=Task(codebook=codebook(),execution_defaults={"thinking":"high","evidence":True})
    id=client.post('/api/tasks',json=t.model_dump()).json()['id']
    out=client.get('/api/tasks/'+id+'/export-cca')
    assert out.status_code==200 and out.json()==codebook()
    assert client.post('/api/tasks/import-cca',json=out.json()).status_code==201
    saved=next(t for t in client.get('/api/tasks').json() if t['id']==id)
    assert saved['spec']['execution_defaults']['thinking']=='high'
    assert saved['spec']['codebook']==codebook()


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


@pytest.mark.parametrize('mutation,path',[
    (lambda d:d.pop('description'), '/description'),
    (lambda d:d.update(version='wrong'), '/version'),
    (lambda d:d['task']['categories'][1].update(id='101'), '/task/categories/1/id'),
    (lambda d:d['examples'][0].update(labels=['unknown']), '/examples/0/labels'),
    (lambda d:d['examples'][0].update(labels=['101','102']), '/examples/0/labels'),
    (lambda d:d.update(language='English'), '/language'),
    (lambda d:d['task']['categories'][0].update(inclusion_criteria=['same','same']), '/task/categories/0/inclusion_criteria'),
])
def test_every_write_and_preview_validates_codebook(client, mutation, path):
    valid={'codebook':codebook()}
    id=client.post('/api/tasks',json=valid).json()['id']
    invalid=copy.deepcopy(valid);mutation(invalid['codebook'])
    for method,url in [('post','/api/tasks'),('put','/api/tasks/'+id+'?revision=1'),('post','/api/tasks/preview')]:
        response=getattr(client,method)(url,json=invalid)
        assert response.status_code==422,response.text
        issues=[issue for e in response.json()['detail'] for issue in e.get('ctx',{}).get('issues',[])]
        assert any(i['path']==path for i in issues),issues
    saved=client.get('/api/tasks').json()
    assert len(saved)==1 and saved[0]['revision']==1 and saved[0]['spec']['codebook']==codebook()


def test_unsupported_task_fields_and_fallback_uses_id(client):
    for invalid in [{'name':'Old task','instructions':'Code','categories':[]},
                   {'codebook':codebook(),'ambiguity_rule':'Rule'},
                   {'codebook':codebook(),'cca_source':codebook()},
                   {'codebook':codebook(),'execution_defaults':{'allow_empty':True}},
                   {'codebook':codebook(),'execution_defaults':{'default_label':'Positive'}}]:
        assert client.post('/api/tasks',json=invalid).status_code==422
    assert client.post('/api/tasks',json={'codebook':codebook(),'execution_defaults':{'default_label':'101'}}).status_code==201


def test_schema_roundtrip_is_lossless_and_not_limited_to_old_task_bounds(client):
    doc=codebook()
    doc['task']['categories']=[{'id':str(i),'label':'Category '+str(i),'definition':'Definition'} for i in range(205)]
    doc['examples']=[{'text':'  Whitespace matters\n','labels':['101'],'explanation':'Explain\nwith lines'}]
    doc['title']='Long title '+('x'*210)
    created=client.post('/api/tasks',json={'codebook':doc,'execution_defaults':{'evidence':True}})
    assert created.status_code==201,created.text
    id=created.json()['id']
    assert client.get('/api/tasks/'+id+'/export-cca').json()==doc
    spec=client.get('/api/tasks').json()[0]['spec']
    assert set(spec)=={'codebook','execution_defaults'}
    assert spec['codebook']==doc


def test_canonical_fewshot_cap_and_execution_override():
    from textlab.jobs import resolved_task
    d=codebook();d['task']['classification_mode']='multi_label'
    d['examples']=[
        {'text':'Both','labels':['101','102'],'explanation':'Mixed tone'},
        {'text':'Positive','labels':['101']},
        {'text':'Negative','labels':['102']}]
    task=Task(codebook=d,execution_defaults={'rationale':True,'thinking':'high'})
    resolved=resolved_task(task,Query(model='m',rationale=False,thinking='off'))
    assert resolved.codebook==task.codebook and task.thinking=='high'
    assert resolved.thinking=='off' and not resolved.rationale
    prompt=messages(task,Query(model='m',examples_per_category=1),'Input')
    assert len(prompt)==2 and 'Both' in prompt[0]['content'] and '"text": "Negative"' not in prompt[0]['content']
    assert len(messages(task,Query(model='m',examples_per_category=0),'Input'))==2


def test_bundled_examples_are_ready_for_fresh_install():
    from pathlib import Path
    from textlab.models import validate_labels
    import csv
    folder=Path(__file__).parents[1]/'examples'
    for name in ['task','task_multi']:
        task=Task.model_validate_json((folder/(name+'.json')).read_text())
        assert to_codebook(task)==json.loads((folder/(name+'.cca.json')).read_text())
    task=Task.model_validate_json((folder/'task_multi.json').read_text())
    with (folder/'gold_multi.csv').open() as source:
        for row in csv.DictReader(source):
            validate_labels(row['annotations'].split('|'),task)
