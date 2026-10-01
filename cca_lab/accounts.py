"""Account registry, revocable cookie sessions, and project authorization."""
import hashlib
import hmac
import os
import logging
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from .db import uid, project_root

router=APIRouter(prefix='/api')
SESSION_SECONDS=12*60*60
log=logging.getLogger('cca_lab.accounts')


def base_root():
    p=Path(os.environ.get('CCA_LAB_DATA','data')).resolve();p.mkdir(parents=True,exist_ok=True);return p


def secret():
    value=os.environ.get('SECRET','')
    if len(value)<32:raise RuntimeError('Set SECRET to a random value of at least 32 characters in .env')
    return value.encode()


@contextmanager
def registry():
    db=sqlite3.connect(base_root()/'accounts.sqlite',timeout=30);db.row_factory=sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:yield db;db.commit()
    except BaseException:db.rollback();raise
    finally:db.close()


def password_hash(password):
    salt=secrets.token_hex(16)
    digest=hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
    return salt+':'+digest


def password_matches(password,encoded):
    salt,digest=encoded.split(':')
    return hmac.compare_digest(digest,hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex())


def token_hash(token):return hmac.new(secret(),token.encode(),hashlib.sha256).hexdigest()


def initialize():
    secret()
    with registry() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,username TEXT UNIQUE COLLATE NOCASE NOT NULL,password TEXT NOT NULL,is_admin INTEGER NOT NULL DEFAULT 0,active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),csrf TEXT NOT NULL,expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,legacy INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS members(project_id TEXT REFERENCES projects(id),user_id TEXT REFERENCES users(id),role TEXT NOT NULL CHECK(role IN ('admin','regular','view')),PRIMARY KEY(project_id,user_id));
        CREATE TABLE IF NOT EXISTS login_limits(key TEXT PRIMARY KEY,count INTEGER NOT NULL,expires REAL NOT NULL);
        ''')
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT 1 FROM users LIMIT 1').fetchone():
            name=os.environ.get('CCA_LAB_ADMIN_USERNAME','admin');password=os.environ.get('CCA_LAB_ADMIN_PASSWORD','')
            validate_credentials(name,password)
            user=uid();project=uid()
            db.execute('INSERT INTO users VALUES(?,?,?,1,1)',(user,name,password_hash(password)))
            db.execute('INSERT INTO projects VALUES(?,?,1,?)',(project,'Default project',time.time()))
            db.execute('INSERT INTO members VALUES(?,?,?)',(project,user,'admin'))
    from .db import init
    init()  # Existing data stays in place and belongs only to the default project.


def validate_credentials(username,password):
    if not re.fullmatch(r'[A-Za-z0-9_.-]{3,64}',username):raise HTTPException(422,'Username: 3–64 letters, digits, underscores, dots or hyphens')
    if not 12<=len(password)<=256:raise HTTPException(422,'Password must contain 12–256 characters')


class Credentials(BaseModel):
    username:str=Field(max_length=64)
    password:str=Field(max_length=256)


def throttle(request,username):
    # Account and peer keys both matter; do not trust forwarded IP headers.
    keys=['ip:'+str(request.client.host if request.client else 'unknown'),'user:'+username.lower()]
    with registry() as db:
        db.execute('BEGIN IMMEDIATE');db.execute('DELETE FROM login_limits WHERE expires<?',(time.time(),))
        for key in keys:
            row=db.execute('SELECT count FROM login_limits WHERE key=?',(key,)).fetchone()
            if row and row[0]>=30:raise HTTPException(429,'Too many attempts; try again in 15 minutes')
        for key in keys:
            db.execute('INSERT INTO login_limits VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1',(key,time.time()+900))


def public_user(row):return {k:row[k] for k in ('id','username','is_admin','active')}


def authenticate(request):
    token=request.cookies.get('cca_session','')
    with registry() as db:
        row=db.execute('SELECT u.*,s.csrf FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>? AND u.active=1',(token_hash(token),time.time())).fetchone()
    if not row:raise HTTPException(401,'Please sign in')
    if request.method not in ('GET','HEAD','OPTIONS'):
        if not hmac.compare_digest(request.headers.get('X-CSRF-Token',''),row['csrf']):raise HTTPException(403,'Invalid CSRF token')
    request.state.user=dict(row)
    return row


def project_path(row):return base_root() if row['legacy'] else base_root()/'projects'/row['id']


def authorize_project(request,user):
    pid=request.headers.get('X-Project-ID') or request.query_params.get('project_id')
    if not pid:raise HTTPException(400,'Select a project')
    with registry() as db:
        row=db.execute('SELECT p.*,m.role FROM projects p JOIN members m ON m.project_id=p.id WHERE p.id=? AND m.user_id=?',(pid,user['id'])).fetchone()
    if not row:raise HTTPException(404,'Project not found')
    if request.method not in ('GET','HEAD','OPTIONS') and row['role']=='view':raise HTTPException(403,'This project is view-only')
    request.state.project=dict(row)
    return project_root.set(project_path(row))


@router.post('/auth/register',status_code=201)
def register(spec:Credentials,request:Request):
    if os.environ.get('CCA_LAB_ALLOW_REGISTRATION','true').lower()!='true':raise HTTPException(403,'Registration is disabled')
    throttle(request,spec.username);validate_credentials(spec.username,spec.password)
    with registry() as db:
        try:db.execute('INSERT INTO users(id,username,password) VALUES(?,?,?)',(uid(),spec.username,password_hash(spec.password)))
        except sqlite3.IntegrityError:raise HTTPException(409,'Username is unavailable')
    return {'registered':True}


@router.post('/auth/login')
def login(spec:Credentials,request:Request,response:Response):
    throttle(request,spec.username)
    with registry() as db:
        user=db.execute('SELECT * FROM users WHERE username=?',(spec.username,)).fetchone()
        encoded=user['password'] if user else ('00'*16+':'+'00'*64)
        if not password_matches(spec.password,encoded) or not user or not user['active']:raise HTTPException(401,'Invalid credentials')
        token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
        db.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
        db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(token_hash(token),user['id'],csrf,time.time()+SESSION_SECONDS))
    response.set_cookie('cca_session',token,httponly=True,samesite='strict',secure=os.environ.get('CCA_LAB_COOKIE_SECURE','false').lower()=='true',max_age=SESSION_SECONDS,path='/')
    return {'user':public_user(user),'csrf':csrf}


@router.get('/auth/me')
def me(request:Request):return {'user':public_user(request.state.user),'csrf':request.state.user['csrf']}


@router.post('/auth/logout')
def logout(request:Request,response:Response):
    with registry() as db:db.execute('DELETE FROM sessions WHERE token=?',(token_hash(request.cookies.get('cca_session','')),))
    response.delete_cookie('cca_session',path='/');return {'ok':True}


class PasswordChange(BaseModel):
    current_password:str=Field(max_length=256)
    password:str=Field(min_length=12,max_length=256)


@router.post('/auth/password')
def change_password(spec:PasswordChange,request:Request):
    user=request.state.user
    with registry() as db:
        row=db.execute('SELECT password FROM users WHERE id=?',(user['id'],)).fetchone()
        if not password_matches(spec.current_password,row[0]):raise HTTPException(403,'Current password is incorrect')
        db.execute('UPDATE users SET password=? WHERE id=?',(password_hash(spec.password),user['id']))
        db.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))
    return {'ok':True}


@router.get('/projects')
def projects(request:Request):
    with registry() as db:return [dict(r) for r in db.execute('SELECT p.id,p.name,m.role FROM projects p JOIN members m ON p.id=m.project_id WHERE m.user_id=? ORDER BY p.created',(request.state.user['id'],))]


class ProjectName(BaseModel):name:str=Field(min_length=1,max_length=120)


@router.post('/projects',status_code=201)
def create_project(spec:ProjectName,request:Request):
    pid=uid()
    from .db import init
    token=project_root.set(base_root()/'projects'/pid)
    try:init()
    finally:project_root.reset(token)
    with registry() as db:
        db.execute('INSERT INTO projects VALUES(?,?,0,?)',(pid,spec.name,time.time()))
        db.execute('INSERT INTO members VALUES(?,?,?)',(pid,request.state.user['id'],'admin'))
    return {'id':pid}


def project_admin(db,pid,user):
    row=db.execute("SELECT 1 FROM members WHERE project_id=? AND user_id=? AND role='admin'",(pid,user['id'])).fetchone()
    if not row:raise HTTPException(403,'Project administrator required')


@router.patch('/projects/{pid}')
def rename_project(pid:str,spec:ProjectName,request:Request):
    with registry() as db:
        project_admin(db,pid,request.state.user);db.execute('UPDATE projects SET name=? WHERE id=?',(spec.name,pid))
    return {'ok':True}


@router.get('/projects/{pid}/members')
def members(pid:str,request:Request):
    with registry() as db:
        project_admin(db,pid,request.state.user)
        return [dict(r) for r in db.execute('SELECT u.id,u.username,u.active,m.role FROM members m JOIN users u ON u.id=m.user_id WHERE m.project_id=?',(pid,))]


class Membership(BaseModel):
    username:str=Field(max_length=64)
    role:str=Field(pattern='^(admin|regular|view)$')


def protect_last_admin(db,pid,user_id):
    row=db.execute("SELECT m.role,u.active FROM members m JOIN users u ON u.id=m.user_id WHERE m.project_id=? AND m.user_id=?",(pid,user_id)).fetchone()
    if row and row[0]=='admin' and row[1] and db.execute("SELECT count(*) FROM members m JOIN users u ON u.id=m.user_id WHERE m.project_id=? AND m.role='admin' AND u.active=1",(pid,)).fetchone()[0]<=1:
        raise HTTPException(409,'Keep at least one active project administrator')


@router.put('/projects/{pid}/members')
def set_member(pid:str,spec:Membership,request:Request):
    with registry() as db:
        db.execute('BEGIN IMMEDIATE');project_admin(db,pid,request.state.user)
        user=db.execute('SELECT id FROM users WHERE username=? AND active=1',(spec.username,)).fetchone()
        if not user:raise HTTPException(404,'Active registered user not found')
        if spec.role!='admin':protect_last_admin(db,pid,user[0])
        db.execute('INSERT INTO members VALUES(?,?,?) ON CONFLICT(project_id,user_id) DO UPDATE SET role=excluded.role',(pid,user[0],spec.role))
    return {'ok':True}


@router.delete('/projects/{pid}/members/{user_id}')
def remove_member(pid:str,user_id:str,request:Request):
    with registry() as db:
        db.execute('BEGIN IMMEDIATE');project_admin(db,pid,request.state.user);protect_last_admin(db,pid,user_id)
        db.execute('DELETE FROM members WHERE project_id=? AND user_id=?',(pid,user_id))
    return {'ok':True}


def site_admin(request):
    if not request.state.user['is_admin']:raise HTTPException(403,'Site administrator required')


@router.get('/admin/users')
def users(request:Request):
    site_admin(request)
    with registry() as db:return [public_user(r) for r in db.execute('SELECT * FROM users ORDER BY username')]


class UserEdit(BaseModel):
    active:bool
    is_admin:bool
    password:str|None=Field(default=None,min_length=12,max_length=256)


@router.patch('/admin/users/{user_id}')
def edit_user(user_id:str,spec:UserEdit,request:Request):
    site_admin(request)
    with registry() as db:
        db.execute('BEGIN IMMEDIATE')
        user=db.execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone()
        if not user:raise HTTPException(404,'User not found')
        if user['is_admin'] and user['active'] and (not spec.is_admin or not spec.active) and db.execute('SELECT count(*) FROM users WHERE is_admin=1 AND active=1').fetchone()[0]<=1:raise HTTPException(409,'Keep an active site administrator')
        if not spec.active:
            for row in db.execute("SELECT project_id FROM members WHERE user_id=? AND role='admin'",(user_id,)).fetchall():protect_last_admin(db,row[0],user_id)
        db.execute('UPDATE users SET active=?,is_admin=? WHERE id=?',(spec.active,spec.is_admin,user_id))
        if spec.password:db.execute('UPDATE users SET password=? WHERE id=?',(password_hash(spec.password),user_id))
        db.execute('DELETE FROM sessions WHERE user_id=?',(user_id,))
    return {'ok':True}


class AccessMiddleware:
    """Scope the entire response lifecycle, including streaming generators."""
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        request=Request(scope);path=request.url.path;token=None
        from starlette.responses import JSONResponse
        from urllib.parse import urlsplit
        try:
            if path.startswith('/api/') and path!='/api/health':
                if request.method not in ('GET','HEAD','OPTIONS'):
                    origin=request.headers.get('origin')
                    if origin and (urlsplit(origin).scheme,urlsplit(origin).netloc)!=(request.url.scheme,request.url.netloc):raise HTTPException(403,'Cross-origin request rejected')
                if path in ('/api/auth/login','/api/auth/register'):
                    if request.method=='POST' and 'application/json' not in request.headers.get('content-type',''):raise HTTPException(415,'JSON required')
                else:
                    user=authenticate(request)
                    if not any(path==p or path.startswith(p+'/') for p in ('/api/auth','/api/projects','/api/admin')):
                        token=authorize_project(request,user)
            elif path=='/api/health' and (request.headers.get('X-Project-ID') or request.query_params.get('project_id')):
                token=authorize_project(request,authenticate(request))
            async def protected_send(message):
                if message['type']=='http.response.start' and path.startswith('/api/'):
                    message['headers']=list(message.get('headers',[]))+[(b'cache-control',b'no-store'),(b'x-content-type-options',b'nosniff')]
                await send(message)
            await self.app(scope,receive,protected_send)
        except HTTPException as exc:
            log.warning('access_rejected method=%s status=%s user_id=%s',request.method,exc.status_code,getattr(request.state,'user',{}).get('id','-'))
            await JSONResponse({'detail':exc.detail},status_code=exc.status_code)(scope,receive,send)
        finally:
            if token is not None:project_root.reset(token)


@router.post('/admin/users',status_code=201)
def create_user(spec:Credentials,request:Request):
    site_admin(request);validate_credentials(spec.username,spec.password)
    with registry() as db:
        try:db.execute('INSERT INTO users(id,username,password) VALUES(?,?,?)',(uid(),spec.username,password_hash(spec.password)))
        except sqlite3.IntegrityError:raise HTTPException(409,'Username is unavailable')
    return {'ok':True}
