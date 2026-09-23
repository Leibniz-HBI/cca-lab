import json
import pytest
from cca_lab.experiment import compile_request
from cca_lab.models import Query,Task,Profile
from test_experiments import BOOK,client,setup,finish

@pytest.mark.parametrize('strategy,category',[('joint',''),('binary','A'),('binary','B')])
@pytest.mark.parametrize('batch_size',[1,2])
def test_compilers_preserve_annotations_and_output_contract(strategy,category,batch_size):
    task=Task(**BOOK);items=[{'id':str(i),'context':'Background','text':'Target'} for i in range(batch_size)]
    settings=dict(model='mock',strategy=strategy,batch_size=batch_size,use_context=True,evidence=True,rationale=True)
    _,roles,_=compile_request(task,Query(**settings,prompt_compiler='roles'),Profile(name='mock',provider='mock'),items,category)
    _,system,_=compile_request(task,Query(**settings,prompt_compiler='system'),Profile(name='mock',provider='mock'),items,category)
    assert [m['role'] for m in system['messages']]==['system','user']
    assert any(m['role']=='assistant' for m in roles['messages'])
    assert roles['messages'][-1]==system['messages'][-1]
    assert roles['response_format']==system['response_format']
    reference=system['messages'][0]['content'].split('# Annotated reference examples\n')[1]
    examples=json.loads(reference[reference.index('\n[')+1:])
    assert examples[0]['text']=='Alpha sample'
    assert examples[0]['context']=='Example context'
    assert examples[0]['labels']==([] if category=='B' else ['A'])
    assert 'evidence' not in examples[0]
    if category:assert 'explanation' not in examples[0]
    else:assert examples[0]['explanation']=='A and B are alternatives'


def test_compilers_separate_evaluation_groups(client):
    _,task,profile,gold,q=setup(client)
    variants=[{'name':compiler,'profile_id':profile,'query':{**q,'prompt_compiler':compiler},'seeds':[1,2]} for compiler in ('roles','system')]
    response=client.post('/api/evaluations',json={'name':'Compilers','task_id':task,'gold_id':gold,'variants':variants})
    assert response.status_code==201,response.text
    eid=response.json()['id'];detail=client.get('/api/evaluations/'+eid).json()
    assert detail['query_count']['runs']==4
    assert {r['query']['prompt_compiler'] for r in detail['runs']}=={'roles','system'}
    report=finish(client,eid)
    assert len(report['groups'])==2
    assert all(g['expected_runs']==2 for g in report['groups'])
