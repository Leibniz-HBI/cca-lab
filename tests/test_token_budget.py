import json
import httpx
import pytest
from cca_lab.models import Query,Task,Profile
from cca_lab.experiment import compile_request,perform
from cca_lab.db import connect
from cca_lab.worker import tick
from test_experiments import BOOK,client,setup

@pytest.mark.parametrize('provider',['openai','ollama'])
@pytest.mark.parametrize('content',[None,'{"results":['])
def test_output_limit_response(provider,content):
    query=Query(model='test',max_tokens=32)
    profile=Profile(name='Test',provider=provider,base_url='http://test')
    items=[{'id':'1','text':'Alpha'}]
    path,body,target=compile_request(Task(**BOOK),query,profile,items)
    message={'content':content,'reasoning':'Still considering the labels'}
    data=({'message':message,'done_reason':'length','eval_count':32} if provider=='ollama'
          else {'choices':[{'message':message,'finish_reason':'length'}],'usage':{'completion_tokens':32}})
    with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,json=data))) as http:
        out=perform(profile,query,target,items,path,body,http)
    assert out['output_limit_reached']
    assert 'token budget exhausted' in out['error']
    assert 'NoneType' not in out['error']
    assert out['results']['1']['status']=='pending'
    assert out['thinking']=='Still considering the labels'


def test_missing_content_without_truncation_is_not_budget_error():
    query=Query(model='test');profile=Profile(name='Test',base_url='http://test')
    items=[{'id':'1','text':'Alpha'}]
    path,body,target=compile_request(Task(**BOOK),query,profile,items)
    data={'choices':[{'message':{'content':None},'finish_reason':'stop'}]}
    with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,json=data))) as http:
        out=perform(profile,query,target,items,path,body,http)
    assert not out['output_limit_reached']
    assert 'No JSON response content' in out['error']


@pytest.mark.parametrize('provider',['mock','ollama'])
def test_retry_budget_doubles_per_component_and_is_logged(client,monkeypatch,provider):
    dataset,task,profile,_,query=setup(client,{'max_tokens':32768,'retries':2,'concurrency':1})
    client.put('/api/profiles/'+profile,json={'name':'Test','provider':provider,'base_url':'http://test'})
    response=client.post('/api/jobs',json=dict(name='Budgets',dataset_id=dataset,task_id=task,profile_id=profile,text_column='text',query=query))
    assert response.status_code==201,response.text
    jid=response.json()['id'];budgets={}
    def fake(profile,q,task,items,path,body,http):
        key=items[0]['id'];seen=budgets.setdefault(key,[]);seen.append(q.max_tokens)
        assert (body['options']['num_predict'] if provider=='ollama' else body['max_tokens'])==q.max_tokens
        limit=key=='1' and len(seen)<=2
        generic=key=='2' and len(seen)==1
        result={'status':'pending','error':'Limit' if limit else 'Invalid label'} if limit or generic else {'status':'ok','labels':['A']}
        return dict(content=None,thinking=None,error=None,prompt_tokens=0,completion_tokens=0,seconds=.01,output_limit_reached=limit,results={key:result})
    monkeypatch.setattr('cca_lab.executor.perform',fake)
    for _ in range(5):tick()
    assert budgets=={'1':[32768,65536,131072],'2':[32768,32768],'3':[32768]}
    with connect() as db:
        snapshot=json.loads(db.execute('SELECT snapshot FROM jobs WHERE id=?',(jid,)).fetchone()[0])
        assert snapshot['query']['max_tokens']==32768
        requests=[json.loads(r[0]) for r in db.execute('SELECT request_json FROM llm_requests WHERE job_id=?',(jid,))]
    key=lambda r:r['options']['num_predict'] if provider=='ollama' else r['max_tokens']
    assert max(map(key,requests))==131072
    assert client.get('/api/jobs/'+jid).json()['status']=='completed'


def test_budget_survives_pause_and_stops_at_retry_limit(client,monkeypatch):
    dataset,task,profile,_,query=setup(client,{'max_tokens':32,'retries':1,'concurrency':1},rows=b'doc_id,text,gold_label,context\n1,Alpha,A,Prior\n')
    response=client.post('/api/jobs',json=dict(name='Pause',dataset_id=dataset,task_id=task,profile_id=profile,text_column='text',query=query))
    jid=response.json()['id'];sent=[]
    def exhausted(profile,q,task,items,path,body,http):
        sent.append(q.max_tokens)
        if len(sent)==1:
            with connect() as db:db.execute("UPDATE jobs SET status='pausing' WHERE id=?",(jid,))
        return dict(content=None,thinking='Thinking',error='Budget exhausted',prompt_tokens=0,completion_tokens=q.max_tokens,seconds=.01,output_limit_reached=True,results={'1':{'status':'pending','error':'Budget exhausted'}})
    monkeypatch.setattr('cca_lab.executor.perform',exhausted)
    tick();tick()
    assert client.get('/api/jobs/'+jid).json()['status']=='paused'
    assert client.post('/api/jobs/'+jid+'/resume').status_code==200
    for _ in range(3):tick()
    assert sent==[32,64]
    result=client.get('/api/jobs/'+jid).json()
    assert result['status']=='completed_with_errors' and result['failed']==1
