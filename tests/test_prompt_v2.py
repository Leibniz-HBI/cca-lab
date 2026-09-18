import json
import httpx
import pytest
from fastapi.testclient import TestClient
from textlab.api import app
from textlab.models import Task, Query, Profile
from textlab.llm import messages, request_body, classify, output_schema, parse_result, example_response
from textlab.legacy_prompt import messages as old_messages
from textlab.db import dumps
from task_fixtures import task_spec


def instrument():
    t=task_spec(name='Sentiment construct',categories=[{'label':'A','definition':'Alpha'},{'label':'B','definition':'Beta'}],
                evidence=True,alternatives=True,rationale=True,confidence=True)
    t['codebook']['authors']=['PRIVATE_METADATA']
    t['codebook']['task']['categories'][0]['inclusion_criteria']=['First\ncontinued','Second']
    t['codebook']['examples']=[{'text':'Alpha','labels':['A'],'explanation':'Explicit alpha','context':'Context provided'}]
    return Task(**t)


def test_reference_examples_do_not_fabricate_annotations():
    t=instrument();prompt=messages(t,Query(model='m'),'Unknown')
    assert [m['role'] for m in prompt]==['system','user']
    system=prompt[0]['content']
    assert system.index('# Classification task')<system.index('# Coding instructions')<system.index('# Categories')<system.index('# Reference examples')<system.index('# Response requirements')
    assert t.codebook['title'] in system and t.codebook['description'] in system
    assert '- First\n  continued\n- Second' in system
    examples=json.loads(system.split('# Reference examples\n')[1].split('\n',1)[1].split('\n\n# Response requirements')[0])
    assert examples==t.codebook['examples']
    assert 'PRIVATE_METADATA' not in system
    assert 'No competing interpretation' not in system
    assert '1.0' not in system
    assert '"evidence"' not in system  # no synthetic response or embedded native schema


@pytest.mark.parametrize('provider',['openai','ollama'])
@pytest.mark.parametrize('mode',['json_schema','json_object','none'])
def test_preview_equals_executed_request(provider,mode,tmp_path,monkeypatch):
    monkeypatch.setenv('TEXTLAB_DATA',str(tmp_path))
    t=instrument();q=Query(model='m',structured_output=mode,retries=0);p=Profile(name='P',provider=provider,base_url='http://localhost')
    with TestClient(app) as client:
        preview=client.post('/api/tasks/preview-request',json={'task':t.model_dump(),'query':q.model_dump(),'provider':provider,'text':'Alpha'})
        assert preview.status_code==200,preview.text
    captured=[]
    def handle(req):
        captured.append(json.loads(req.content))
        content=dumps(example_response(t,'Alpha',['A'],'Alpha'))
        return httpx.Response(200,json={'message':{'content':content}} if provider=='ollama' else {'choices':[{'message':{'content':content}}]})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result=classify({'task':t.model_dump(),'query':q.model_dump(),'profile':p.model_dump()},'Alpha',client)
    assert result['status']=='ok'
    assert result['attempt_outputs'][0]['prompt_protocol']=='cca-reference-v2'
    assert captured[0]==preview.json()['request']
    assert ('Output JSON Schema:' in captured[0]['messages'][0]['content'])==(mode!='json_schema')
    if mode=='json_schema':
        native=captured[0]['format'] if provider=='ollama' else captured[0]['response_format']['json_schema']['schema']
        assert native==output_schema(t)


def test_empty_boundary_valid_but_wrong_types_and_missing_fields_fail():
    task=instrument();obj=example_response(task,'Alpha',['A'],'Alpha')
    assert obj['candidate_interpretations'][0]['boundary_note']==''
    parse_result(dumps(obj),task,'Alpha')
    obj['candidate_interpretations'][0]['boundary_note']=None
    with pytest.raises(ValueError):parse_result(dumps(obj),task,'Alpha')


def test_legacy_snapshot_uses_frozen_compiler():
    t=instrument();q=Query(model='m')
    assert messages(t,q,'Alpha','evidence-first-v1')==old_messages(t,q,'Alpha')
    path,body=request_body(t,q,Profile(name='P'), 'Alpha','evidence-first-v1')
    assert len(body['messages'])==4
    assert body['response_format']['json_schema']['schema']['properties']['candidate_interpretations']['items']['properties']['boundary_note']['minLength']==1


def test_paired_configuration_and_protocol_grouping():
    import importlib.util
    from pathlib import Path
    from textlab.repetitions import experiment_key
    spec=importlib.util.spec_from_file_location('compare',Path(__file__).parents[1]/'scripts/compare_prompts.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    original={'name':'Held out','gold_id':'gold','task_id':'task','seeds':[11,22],
              'variants':[{'name':'Model','profile_id':'p','query':{'model':'m','temperature':.2}}]}
    paired=module.paired_request(original)
    assert paired['seeds']==original['seeds'] and len(paired['variants'])==2
    left,right=paired['variants']
    assert left['query']['prompt_protocol']=='evidence-first-v1'
    assert right['query']['prompt_protocol']=='cca-reference-v2'
    assert 'prompt_protocol' not in original['variants'][0]['query']
    assert experiment_key({'task':instrument().model_dump(),'query':left['query']})!=experiment_key({'task':instrument().model_dump(),'query':right['query']})


def test_top_level_legacy_protocol_controls_resumed_requests():
    t=instrument();q=Query(model='m',retries=0);p=Profile(name='P',base_url='http://localhost')
    captured=[]
    def handle(req):
        captured.append(json.loads(req.content))
        obj=example_response(t,'Alpha',['A'],'Alpha')
        obj['candidate_interpretations'][0]['boundary_note']='No concern.'
        return httpx.Response(200,json={'choices':[{'message':{'content':dumps(obj)}}]})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result=classify({'task':t.model_dump(),'query':q.model_dump(),'profile':p.model_dump(),
                         'prompt_protocol':'evidence-first-v1'},'Alpha',client)
    assert result['status']=='ok' and result['attempt_outputs'][0]['prompt_protocol']=='evidence-first-v1'
    assert captured[0]['messages']==old_messages(t,q,'Alpha')
