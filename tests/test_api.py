import os
import tempfile
from pathlib import Path

os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(tempfile.gettempdir()) / ('infrapass-test-' + str(os.getpid()) + '.db'))
os.environ['APP_ORIGIN'] = 'http://testserver'
os.environ['COOKIE_SECURE'] = 'false'
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app, Base, Certificate, Session, User, engine

import pytest
@pytest.fixture(autouse=True)
def database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Certificate(slug='cka', data={'slug':'cka','name':'CKA'})); s.commit()
    yield

def client(): return TestClient(app, headers={'origin':'http://testserver'})
def signup(c, email='a@example.com'):
    r=c.post('/api/auth/register',json={'email':email,'password':'safe-password-123','name':'테스터'})
    assert r.status_code==201

def test_auth_csrf_and_shared_session():
    c=client(); signup(c)
    assert c.get('/api/me').json()['name']=='테스터'
    other=client(); other.cookies.update(c.cookies)
    assert other.get('/api/me').status_code==200
    assert c.post('/api/auth/logout',headers={'origin':'https://evil.test'},json={}).status_code==403
    assert c.get('/api/admin/reports').status_code==403
    c.post('/api/auth/logout',json={})
    assert other.get('/api/me').status_code==401

def test_bookmarks_are_private_and_idempotent():
    c=client();signup(c)
    assert c.put('/api/bookmarks/cka').status_code==200
    c.put('/api/bookmarks/cka')
    assert c.get('/api/bookmarks').json()==['cka']
    other=client(); signup(other,'other@example.com')
    assert other.get('/api/bookmarks').json()==[]
    assert c.put('/api/bookmarks/missing').status_code==404
    c.delete('/api/bookmarks/cka')
    assert c.get('/api/bookmarks').json()==[]

def test_post_replay_and_comments():
    c=client();signup(c)
    p={'certificate':'cka','kind':'후기','title':'준비 후기','body':'공식 문서를 읽으며 준비했습니다.','request_id':'request-1234567890','details':{'결과':'합격'}}
    first=c.post('/api/posts',json=p)
    assert first.status_code==201
    assert c.post('/api/posts',json=p).json()==first.json()
    assert len(c.get('/api/posts').json())==1
    pid=first.json()['id']
    assert c.post(f'/api/posts/{pid}/comments',json={'body':'감사합니다'}).status_code==201
    assert len(c.get(f'/api/posts/{pid}/comments').json())==1
    assert client().post('/api/posts',json=p).status_code==401

def test_admin_and_reports():
    c=client();signup(c)
    assert c.post('/api/certificates/cka/reports',json={'body':'공식 시험 정보 변경 제보'}).status_code==201
    with Session(engine) as s:
        u=s.scalar(select(User));u.admin=True;s.commit()
    assert len(c.get('/api/admin/reports').json())==1
    assert c.put('/api/admin/certificates/cka',json={'source':'javascript:alert(1)'}).status_code==422
    assert c.put('/api/admin/certificates/cka',json={'exam':'공식 시험 정보','verified_at':'2026-09-11'}).status_code==200
    assert c.get('/api/certificates/cka').json()['exam']=='공식 시험 정보'

def test_invalid_login_and_catalog():
    c=client(); signup(c)
    assert c.post('/api/auth/login',json={'email':'a@example.com','password':'incorrect-password'}).status_code==401
    assert c.get('/api/certificates').status_code==200
    assert c.get('/api/health/ready').status_code==200
    assert c.get('/').status_code==200
