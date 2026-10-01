"""Existing single-project tests sign in through the real authentication API."""
import pytest
from fastapi.testclient import TestClient

@pytest.fixture(autouse=True)
def authenticated_test_defaults(monkeypatch,request):
    monkeypatch.setenv('SECRET','test-only-secret-32-characters-minimum-1234')
    monkeypatch.setenv('CCA_LAB_ADMIN_USERNAME','admin')
    monkeypatch.setenv('CCA_LAB_ADMIN_PASSWORD','test-password-123456')
    if request.node.get_closest_marker('access_control'):return
    original=TestClient.__enter__
    def enter(client):
        result=original(client)
        login=client.post('/api/auth/login',json={'username':'admin','password':'test-password-123456'})
        assert login.status_code==200,login.text
        client.headers['X-CSRF-Token']=login.json()['csrf']
        projects=client.get('/api/projects').json();client.headers['X-Project-ID']=projects[0]['id']
        return result
    monkeypatch.setattr(TestClient,'__enter__',enter)
