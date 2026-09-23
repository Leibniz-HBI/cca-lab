import json
import sqlite3
from cca_lab.error_stats import error_statistics
from test_experiments import client,setup


def test_error_counts_retries_outcomes_and_job_isolation():
    db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
    db.execute('CREATE TABLE results(job_id,row_no,status,error,attempt_outputs,error_count)')
    def add(row,status,errors,final=None,job='a'):
        db.execute('INSERT INTO results VALUES(?,?,?,?,?,?)',(job,row,status,final,json.dumps([{'error':e} for e in errors]),sum(bool(e) for e in errors)))
    add(1,'ok',['Invalid evidence','Invalid evidence',None])
    add(2,'failed',['Invalid evidence','Invalid JSON'],'Invalid JSON')
    add(3,'fallback',['Invalid JSON'],'Invalid JSON')
    add(4,'failed',[],'Empty text')
    add(5,'ok',[None])
    add(1,'failed',['Other error'],'Other error',job='other')
    stats=error_statistics(db,'a')
    assert {k:v for k,v in stats.items() if k!='by_error'}==dict(documents=4,recovered=1,failed=2,fallbacks=1,occurrences=6)
    assert stats['by_error']==[
        dict(message='Invalid evidence',occurrences=3,documents=2,recovered=1,failed=1,fallbacks=0),
        dict(message='Invalid JSON',occurrences=2,documents=2,recovered=0,failed=1,fallbacks=1),
        dict(message='Empty text',occurrences=1,documents=1,recovered=0,failed=1,fallbacks=0)]
    assert error_statistics(db,'missing')==dict(documents=0,recovered=0,failed=0,fallbacks=0,occurrences=0,by_error=[])


def test_job_detail_exposes_error_statistics(client):
    dataset,task,profile,_,query=setup(client)
    response=client.post('/api/jobs',json=dict(name='Statistics',dataset_id=dataset,task_id=task,profile_id=profile,text_column='text',query=query))
    assert response.status_code==201,response.text
    result=client.get('/api/jobs/'+response.json()['id']).json()
    assert result['error_statistics']['by_error']==[]
    assert result['error_statistics']['documents']==0
