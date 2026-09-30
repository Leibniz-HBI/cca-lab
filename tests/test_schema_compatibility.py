import json
import pytest
from cca_lab.models import Task,Query,Profile,validate_labels
from cca_lab.jobs import resolved_task
from cca_lab.experiment import compile_request
from cca_lab.llm import parse_result
from test_experiments import BOOK

@pytest.mark.parametrize('provider',['openai','ollama'])
@pytest.mark.parametrize('compiler',['roles','system'])
@pytest.mark.parametrize('strategy',['joint','binary'])
def test_runtime_schema_omits_unique_items(provider,compiler,strategy):
    query=Query(model='test',prompt_compiler=compiler,strategy=strategy,alternatives=True,batch_size=2)
    _,body,_=compile_request(Task(**BOOK),query,Profile(name='test',provider=provider),
                           [{'id':'1','text':'Alpha'},{'id':'2','text':'Beta'}], 'A' if strategy=='binary' else '')
    assert 'uniqueItems' not in json.dumps(body)
    schema=body['format'] if provider=='ollama' else body['response_format']['json_schema']['schema']
    labels=schema['properties']['results']['items']['properties']['labels']
    assert labels['minItems']==0
    assert labels['maxItems']==(1 if strategy=='binary' else 2)
    assert labels['items']['enum']==(['A'] if strategy=='binary' else ['A','B'])


def test_response_deduplication_and_candidate_matching():
    task=resolved_task(Task(**BOOK),Query(model='test',alternatives=True))
    candidate=lambda labels:dict(labels=labels,justification='Supported',supporting_quotes=[],boundary_note='')
    response={'labels':['B','A','B','A'],'candidate_interpretations':[candidate(['A','B','A']),candidate(['B','B'])]}
    result=parse_result(json.dumps(response),task,'Alpha Beta')
    assert result['labels']==['B','A']
    assert result['candidate_interpretations'][0]['labels']==['A','B']
    assert result['alternative_interpretations'][0]['labels']==['B']
    # Gold/codebook validation remains strict; only model outputs are normalized.
    with pytest.raises(ValueError):validate_labels(['A','A'],task)

@pytest.mark.parametrize('labels',[['UNKNOWN','UNKNOWN'],[{}],['A',1],'A'])
def test_invalid_labels_still_rejected(labels):
    with pytest.raises(ValueError):parse_result(json.dumps({'labels':labels}),Task(**BOOK))


def test_single_label_cardinality_after_normalization():
    book=json.loads(json.dumps(BOOK));book['codebook']['task']['classification_mode']='single_label'
    task=Task(**book)
    assert parse_result('{"labels":["A","A"]}',task)['labels']==['A']
    with pytest.raises(ValueError):parse_result('{"labels":["A","B","A"]}',task)
