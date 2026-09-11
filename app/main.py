import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pwdlib import PasswordHash
from sqlalchemy import (JSON, Boolean, DateTime, ForeignKey, Integer, String,
                        Text, UniqueConstraint, create_engine, select, text)
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

load_dotenv()
url = os.getenv('DATABASE_URL') or URL.create('mysql+pymysql',
    username=os.getenv('DB_USER', 'infrapass'), password=os.getenv('DB_PASSWORD', ''),
    host=os.getenv('DB_HOST', '192.168.23.7'), port=int(os.getenv('DB_PORT', '3306')),
    database=os.getenv('DB_NAME', 'infrapass'), query={'charset': 'utf8mb4'})
engine = create_engine(url, pool_pre_ping=True, pool_recycle=1800,
    **({'connect_args': {'check_same_thread': False}} if str(url).startswith('sqlite') else
       {'pool_size': 5, 'max_overflow': 5, 'connect_args': {'connect_timeout': 5, 'read_timeout': 15, 'write_timeout': 15}}))

class Base(DeclarativeBase): pass
class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(190), unique=True)
    name: Mapped[str] = mapped_column(String(40))
    password: Mapped[str] = mapped_column(String(255))
    admin: Mapped[bool] = mapped_column(Boolean, default=False)
class Login(Base):
    __tablename__ = 'sessions'
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    expires: Mapped[datetime] = mapped_column(DateTime)
class Certificate(Base):
    __tablename__ = 'certificates'
    slug: Mapped[str] = mapped_column(String(100), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)
class Post(Base):
    __tablename__ = 'posts'
    __table_args__ = (UniqueConstraint('user_id', 'request_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    certificate: Mapped[str] = mapped_column(ForeignKey('certificates.slug'))
    kind: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    request_id: Mapped[str] = mapped_column(String(64))
    created: Mapped[datetime] = mapped_column(default=datetime.utcnow)
class Comment(Base):
    __tablename__ = 'comments'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    post_id: Mapped[int] = mapped_column(ForeignKey('posts.id'))
    body: Mapped[str] = mapped_column(Text)
    created: Mapped[datetime] = mapped_column(default=datetime.utcnow)
class Bookmark(Base):
    __tablename__ = 'bookmarks'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    certificate: Mapped[str] = mapped_column(ForeignKey('certificates.slug'), primary_key=True)
class Report(Base):
    __tablename__ = 'reports'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    certificate: Mapped[str] = mapped_column(ForeignKey('certificates.slug'))
    body: Mapped[str] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(default=False)
class Audit(Base):
    __tablename__ = 'audit'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    certificate: Mapped[str] = mapped_column(String(100))
    before: Mapped[dict] = mapped_column(JSON)
    created: Mapped[datetime] = mapped_column(default=datetime.utcnow)

app = FastAPI(title='InfraPass API', docs_url=None, redoc_url=None)
passwords = PasswordHash.recommended()
def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)
def db():
    with Session(engine) as s: yield s
def user(request: Request, s: Session = Depends(db)):
    token = request.cookies.get('ip_session', '')
    login = s.get(Login, hashlib.sha256(token.encode()).hexdigest()) if token else None
    if not login or login.expires < utcnow(): raise HTTPException(401, '로그인이 필요합니다.')
    return s.get(User, login.user_id)
def admin(u: User = Depends(user)):
    if not u.admin: raise HTTPException(403, '관리자 권한이 필요합니다.')
    return u
@app.middleware('http')
async def csrf(request, call_next):
    if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        if request.headers.get('origin') != os.getenv('APP_ORIGIN', 'http://127.0.0.1:8000'):
            return JSONResponse({'detail': '허용되지 않은 요청 출처입니다.'}, status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    if request.url.path.startswith('/api'): response.headers['Cache-Control'] = 'no-store'
    return response
@app.exception_handler(OperationalError)
async def unavailable(request, exc):
    return JSONResponse({'detail': 'DB 연결을 복구 중입니다. 잠시 후 다시 확인해 주세요.'}, status_code=503, headers={'Retry-After': '5'})
@app.get('/api/health/live')
def live(): return {'status': 'ok'}
@app.get('/api/health/ready')
def ready(s: Session = Depends(db)):
    s.execute(text('SELECT 1'))
    return {'status': 'ready'}

class Credentials(BaseModel):
    email: str = Field(min_length=5, max_length=190, pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    password: str = Field(min_length=10, max_length=128)
    name: str = Field(default='학습자', min_length=2, max_length=40)
def profile(u): return {'id': u.id, 'name': u.name, 'admin': u.admin}
def issue(u, response, s):
    token = secrets.token_urlsafe(32)
    s.add(Login(token=hashlib.sha256(token.encode()).hexdigest(), user_id=u.id, expires=utcnow()+timedelta(days=7)))
    s.commit()
    response.set_cookie('ip_session', token, httponly=True, secure=os.getenv('COOKIE_SECURE', 'true') == 'true', samesite='lax', max_age=604800)
    return profile(u)
@app.post('/api/auth/register', status_code=201)
def register(c: Credentials, response: Response, s: Session = Depends(db)):
    if len(c.name.strip()) < 2: raise HTTPException(422, '닉네임은 공백을 제외하고 2자 이상 입력하세요.')
    u = User(email=c.email.lower().strip(), name=c.name.strip(), password=passwords.hash(c.password))
    s.add(u)
    try: s.commit()
    except IntegrityError:
        s.rollback(); raise HTTPException(409, '이미 등록된 이메일입니다.')
    return issue(u, response, s)
@app.post('/api/auth/login')
def login(c: Credentials, response: Response, s: Session = Depends(db)):
    u = s.scalar(select(User).where(User.email == c.email.lower().strip()))
    if not u or not passwords.verify(c.password, u.password): raise HTTPException(401, '이메일 또는 비밀번호를 확인하세요.')
    return issue(u, response, s)
@app.post('/api/auth/logout')
def logout(request: Request, response: Response, s: Session = Depends(db)):
    token = request.cookies.get('ip_session', '')
    row = s.get(Login, hashlib.sha256(token.encode()).hexdigest())
    if row: s.delete(row); s.commit()
    response.delete_cookie('ip_session')
    return {'ok': True}
@app.get('/api/me')
def me(u: User = Depends(user)): return profile(u)
@app.get('/api/certificates')
def certificates(s: Session = Depends(db)):
    return [c.data for c in s.scalars(select(Certificate).order_by(Certificate.slug))]
@app.get('/api/certificates/{slug}')
def certificate(slug: str, s: Session = Depends(db)):
    c = s.get(Certificate, slug)
    if not c: raise HTTPException(404, '자격증을 찾을 수 없습니다.')
    return c.data
@app.get('/api/bookmarks')
def bookmarks(u: User = Depends(user), s: Session = Depends(db)):
    return list(s.scalars(select(Bookmark.certificate).where(Bookmark.user_id == u.id)))
@app.put('/api/bookmarks/{slug}')
def save(slug: str, u: User = Depends(user), s: Session = Depends(db)):
    if not s.get(Certificate, slug): raise HTTPException(404)
    if not s.get(Bookmark, (u.id, slug)):
        s.add(Bookmark(user_id=u.id, certificate=slug))
        try: s.commit()
        except IntegrityError: s.rollback()
    return {'ok': True}
@app.delete('/api/bookmarks/{slug}')
def unsave(slug: str, u: User = Depends(user), s: Session = Depends(db)):
    b = s.get(Bookmark, (u.id, slug))
    if b: s.delete(b); s.commit()
    return {'ok': True}
class PostInput(BaseModel):
    certificate: str
    kind: Literal['후기', '질문', '공부 기록', '스터디']
    title: str = Field(min_length=2, max_length=160)
    body: str = Field(min_length=10, max_length=15000)
    request_id: str = Field(min_length=16, max_length=64)
    details: dict[str, str] = Field(default_factory=dict, max_length=12)
@app.get('/api/posts')
def posts(certificate: str = '', kind: str = '', offset: int = 0, s: Session = Depends(db)):
    q = select(Post, User.name).join(User, User.id == Post.user_id)
    if certificate: q = q.where(Post.certificate == certificate)
    if kind: q = q.where(Post.kind == kind)
    rows = s.execute(q.order_by(Post.id.desc()).offset(max(0, offset)).limit(30))
    return [dict(id=p.id, certificate=p.certificate, kind=p.kind, title=p.title, body=p.body, details=p.details, author=n, created=p.created.isoformat()+'Z') for p,n in rows]
@app.post('/api/posts', status_code=201)
def create_post(p: PostInput, u: User = Depends(user), s: Session = Depends(db)):
    if any(len(v) > 2000 for v in p.details.values()): raise HTTPException(422, '후기 항목이 너무 깁니다.')
    if not s.get(Certificate, p.certificate): raise HTTPException(404)
    old = s.scalar(select(Post).where(Post.user_id == u.id, Post.request_id == p.request_id))
    if old: return {'id': old.id}
    row = Post(user_id=u.id, **p.model_dump()); s.add(row)
    try: s.commit()
    except IntegrityError:
        s.rollback()
        old = s.scalar(select(Post).where(Post.user_id == u.id, Post.request_id == p.request_id))
        if old: return {'id': old.id}
        raise
    return {'id': row.id}
class BodyInput(BaseModel):
    body: str = Field(min_length=2, max_length=5000)
@app.get('/api/posts/{post_id}/comments')
def comments(post_id: int, s: Session = Depends(db)):
    return [dict(id=c.id, body=c.body, author=n) for c,n in s.execute(select(Comment, User.name).join(User, User.id == Comment.user_id).where(Comment.post_id == post_id).order_by(Comment.id))]
@app.post('/api/posts/{post_id}/comments', status_code=201)
def add_comment(post_id: int, b: BodyInput, u: User = Depends(user), s: Session = Depends(db)):
    if not s.get(Post, post_id): raise HTTPException(404)
    c = Comment(post_id=post_id, user_id=u.id, body=b.body); s.add(c); s.commit()
    return {'id': c.id}
@app.post('/api/certificates/{slug}/reports', status_code=201)
def report(slug: str, b: BodyInput, u: User = Depends(user), s: Session = Depends(db)):
    if not s.get(Certificate, slug): raise HTTPException(404)
    r = Report(user_id=u.id, certificate=slug, body=b.body); s.add(r); s.commit()
    return {'id': r.id}
@app.get('/api/admin/reports')
def reports(u: User = Depends(admin), s: Session = Depends(db)):
    return [dict(id=r.id, certificate=r.certificate, body=r.body, resolved=r.resolved) for r in s.scalars(select(Report).order_by(Report.id.desc()).limit(100))]
@app.patch('/api/admin/reports/{rid}')
def resolve(rid: int, u: User = Depends(admin), s: Session = Depends(db)):
    r = s.get(Report, rid)
    if not r: raise HTTPException(404)
    r.resolved = True; s.commit(); return {'ok': True}
@app.put('/api/admin/certificates/{slug}')
def edit(slug: str, data: dict, u: User = Depends(admin), s: Session = Depends(db)):
    c = s.get(Certificate, slug)
    if not c: raise HTTPException(404)
    allowed = {'summary','audience','process','study','exam','renewal','verified_at','status','events'}
    if set(data) - allowed: raise HTTPException(422, '수정할 수 없는 필드입니다.')
    import json
    if len(json.dumps(data)) > 30000: raise HTTPException(422)
    if any(not isinstance(v, str) for k,v in data.items() if k != 'events'): raise HTTPException(422)
    if data.get('verified_at'):
        try: datetime.strptime(data['verified_at'], '%Y-%m-%d')
        except ValueError: raise HTTPException(422, '확인일은 YYYY-MM-DD 형식이어야 합니다.')
    if 'events' in data:
        if not isinstance(data['events'], list): raise HTTPException(422)
        for event in data['events']:
            if not isinstance(event, dict) or set(event) != {'date','title'}: raise HTTPException(422)
            try: datetime.strptime(event['date'], '%Y-%m-%d')
            except (ValueError, TypeError): raise HTTPException(422)
            if not isinstance(event['title'], str): raise HTTPException(422)
    s.add(Audit(user_id=u.id, certificate=slug, before=c.data))
    c.data = {**c.data, **data}; s.commit(); return c.data

# Development only: production Nginx serves this folder directly.
app.mount('/', StaticFiles(directory=Path(__file__).resolve().parent.parent/'web', html=True), name='web')
