import concurrent.futures
import pytest
from fastapi.testclient import TestClient
from cca_lab.api import app
from cca_lab.accounts import registry
from test_experiments import BOOK

pytestmark=pytest.mark.access_control

@pytest.fixture
def server(tmp_path,monkeypatch):
    monkeypatch.setenv('CCA_LAB_DATA',str(tmp_path))
    with TestClient(app) as c:yield c


def sign_in(c,name='admin',password='test-password-123456'):
    c.cookies.clear();c.headers.pop('X-Project-ID',None);c.headers.pop('X-CSRF-Token',None)
    r=c.post('/api/auth/login',json={'username':name,'password':password});assert r.status_code==200,r.text
    c.headers['X-CSRF-Token']=r.json()['csrf'];return r.json()['user']


def test_authentication_csrf_revocation(server):
    c=server
    assert c.get('/api/tasks').status_code==401
    assert c.post('/api/auth/login',json={'username':'admin','password':'wrong'}).status_code==401
    sign_in(c);pid=c.get('/api/projects').json()[0]['id'];c.headers['X-Project-ID']=pid
    assert c.get('/api/tasks').status_code==200
    csrf=c.headers.pop('X-CSRF-Token');assert c.post('/api/tasks',json=BOOK).status_code==403
    c.headers['X-CSRF-Token']=csrf
    assert c.post('/api/tasks',json=BOOK,headers={'Origin':'https://attacker.example'}).status_code==403
    assert c.post('/api/auth/logout').status_code==200
    assert c.get('/api/tasks').status_code==401


def test_project_isolation_roles_and_streams(server):
    c=server;sign_in(c)
    first=c.get('/api/projects').json()[0]['id'];c.headers['X-Project-ID']=first
    task=c.post('/api/tasks',json=BOOK).json()['id']
    data=c.post('/api/datasets',content=b'text\nAlpha\n').json()['id']
    second=c.post('/api/projects',json={'name':'Second'}).json()['id'];c.headers['X-Project-ID']=second
    assert c.get('/api/tasks').json()==[]
    assert c.get('/api/tasks/'+task).status_code==404
    assert c.delete('/api/tasks/'+task).status_code==404
    assert c.get('/api/datasets/'+data+'/preview').status_code==404
    # Explicit project selection, never an implicit shared workspace.
    del c.headers['X-Project-ID'];assert c.get('/api/tasks').status_code==400
    assert len(c.get('/api/tasks?project_id='+first).json())==1
    assert c.post('/api/auth/register',json={'username':'reader','password':'reader-password-123'}).status_code==201
    assert c.put('/api/projects/'+first+'/members',json={'username':'reader','role':'view'}).status_code==200
    sign_in(c,'reader','reader-password-123');c.headers['X-Project-ID']=first
    assert len(c.get('/api/tasks').json())==1
    assert c.post('/api/tasks',json=BOOK).status_code==403
    assert c.delete('/api/tasks/'+task).status_code==403
    assert c.get('/api/projects/'+first+'/members').status_code==403
    assert c.get('/api/admin/users').status_code==403
    assert c.get('/api/tasks',headers={'X-Project-ID':second}).status_code==404
    assert c.get('/api/tasks?project_id='+second,headers={'X-Project-ID':second}).status_code==404
    sign_in(c);assert c.put('/api/projects/'+first+'/members',json={'username':'reader','role':'regular'}).status_code==200
    sign_in(c,'reader','reader-password-123');c.headers['X-Project-ID']=first
    assert c.post('/api/tasks',json=BOOK).status_code==201
    assert c.put('/api/projects/'+first+'/members',json={'username':'reader','role':'admin'}).status_code==403
    own=c.post('/api/projects',json={'name':'Own project'});assert own.status_code==201
    assert c.get('/api/projects/'+own.json()['id']+'/members').json()[0]['role']=='admin'


def test_admin_safety_and_password_reset(server):
    c=server;admin=sign_in(c);pid=c.get('/api/projects').json()[0]['id']
    assert c.patch('/api/admin/users/'+admin['id'],json={'active':False,'is_admin':True}).status_code==409
    assert c.delete('/api/projects/'+pid+'/members/'+admin['id']).status_code==409
    assert c.post('/api/auth/register',json={'username':'member','password':'member-password-123'}).status_code==201
    c.put('/api/projects/'+pid+'/members',json={'username':'member','role':'regular'})
    member=sign_in(c,'member','member-password-123');old_session=c.cookies.get('cca_session')
    sign_in(c)
    assert c.patch('/api/admin/users/'+member['id'],json={'active':True,'is_admin':False,'password':'changed-password-123'}).status_code==200
    c.cookies.set('cca_session',old_session,domain='testserver.local',path='/')
    assert c.get('/api/auth/me').status_code==401
    sign_in(c,'member','changed-password-123')
    assert c.post('/api/auth/password',json={'current_password':'changed-password-123','password':'new-password-12345'}).status_code==200
    assert c.get('/api/auth/me').status_code==401


def test_parallel_project_contexts_do_not_leak(server):
    c=server;sign_in(c)
    a=c.get('/api/projects').json()[0]['id'];b=c.post('/api/projects',json={'name':'B'}).json()['id']
    c.headers['X-Project-ID']=a;c.post('/api/tasks',json=BOOK)
    def fetch(pid):return c.get('/api/tasks',headers={'X-Project-ID':pid}).json()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(fetch,[a,b]*10))
    assert [len(r) for r in results]==[1,0]*10


def test_revoked_membership_and_download_authorization(server):
    c=server;sign_in(c);pid=c.get('/api/projects').json()[0]['id']
    c.headers['X-Project-ID']=pid
    task=c.post('/api/tasks',json=BOOK).json()['id']
    c.post('/api/auth/register',json={'username':'viewer','password':'viewer-password-123'})
    c.put('/api/projects/'+pid+'/members',json={'username':'viewer','role':'view'})
    viewer=sign_in(c,'viewer','viewer-password-123');cookie=c.cookies.get('cca_session');csrf=c.headers['X-CSRF-Token']
    url='/api/tasks/'+task+'/export-cca?project_id='+pid
    assert c.get(url).status_code==200
    sign_in(c)
    assert c.delete('/api/projects/'+pid+'/members/'+viewer['id']).status_code==200
    c.cookies.set('cca_session',cookie,domain='testserver.local',path='/');c.headers['X-CSRF-Token']=csrf
    assert c.get('/api/auth/me').status_code==200
    assert c.get(url).status_code==404
    assert c.get('/api/projects').json()==[]
    assert c.post('/api/jobs/anything/resume',headers={'X-Project-ID':pid}).status_code==404


def test_registration_controls_account_disable_and_secret_rotation(server,monkeypatch):
    c=server;sign_in(c)
    monkeypatch.setenv('CCA_LAB_ALLOW_REGISTRATION','false')
    assert c.post('/api/auth/register',json={'username':'blocked','password':'blocked-password-123'}).status_code==403
    assert c.post('/api/admin/users',json={'username':'staff','password':'staff-password-123'}).status_code==201
    staff=sign_in(c,'staff','staff-password-123');cookie=c.cookies.get('cca_session')
    sign_in(c)
    assert c.patch('/api/admin/users/'+staff['id'],json={'active':False,'is_admin':False}).status_code==200
    c.cookies.set('cca_session',cookie,domain='testserver.local',path='/')
    assert c.get('/api/auth/me').status_code==401
    assert c.post('/api/auth/login',json={'username':'staff','password':'staff-password-123'}).status_code==401
    sign_in(c)
    monkeypatch.setenv('SECRET','rotated-secret-at-least-32-characters-12345')
    assert c.get('/api/auth/me').status_code==401


def test_profile_cannot_read_application_secrets(server):
    c=server;sign_in(c);c.headers['X-Project-ID']=c.get('/api/projects').json()[0]['id']
    for name in ('SECRET','CCA_LAB_ADMIN_PASSWORD','PATH'):
        assert c.post('/api/profiles',json={'name':'Invalid','provider':'mock','api_key_env':name}).status_code==422
    assert c.post('/api/profiles',json={'name':'Allowed','provider':'mock','api_key_env':'LLM_API_KEY'}).status_code==201
