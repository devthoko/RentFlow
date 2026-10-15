import hashlib, secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.templating import Jinja2Templates
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from .config import Config
from .db import make_engine, transaction
from .models import User, Setting, LoginAttempt, now
from .security import password_hash, password_valid, email

ROOT = Path(__file__).parent
views = Jinja2Templates(directory=str(ROOT / 'templates'))
def eur(cents): return f'{(cents or 0)/100:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.') + ' €'
views.env.filters['eur'] = eur

def current_user(request, db):
    user = db.get(User, request.session.get('uid', 0))
    if not user or not user.active or user.version != request.session.get('version'): return None
    return user

def require_user(request, db, admin=False):
    user = current_user(request, db)
    if not user: raise HTTPException(401, 'Bitte anmelden.')
    if admin and user.role != 'admin': raise HTTPException(403, 'Nur Administratoren dürfen diese Einstellung ändern.')
    return user

def csrf(request, data):
    supplied = request.headers.get('X-CSRF-Token') or data.get('csrf', '')
    expected = request.session.get('csrf', '')
    if not expected or not secrets.compare_digest(str(supplied), expected):
        raise HTTPException(403, 'Sicherheitsprüfung fehlgeschlagen. Bitte die Seite neu laden.')

def render(request, template, **context):
    request.session.setdefault('csrf', secrets.token_urlsafe(32))
    with Session(request.app.state.engine) as db: user = current_user(request, db)
    return views.TemplateResponse(request=request, name=template, context={
        'user': user, 'csrf': request.session['csrf'], 'op_key': secrets.token_urlsafe(24),
        'flash': request.session.pop('flash', None), **context})

def redirect(request, path, message=None):
    if message: request.session['flash'] = message
    return RedirectResponse(path, status_code=303)

def create_app(config=None):
    config = config or Config.environment()
    app = FastAPI(title='RentFlow', docs_url=None, redoc_url=None)
    app.state.config = config
    app.state.engine = make_engine(config.data)
    app.add_middleware(SessionMiddleware, secret_key=config.secret, session_cookie='rentflow',
                       same_site='lax', https_only=config.secure_cookie, max_age=28800)
    app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')

    @app.middleware('http')
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'"
        response.headers['Cache-Control'] = 'no-store' if not request.url.path.startswith('/static/') else 'public, max-age=86400'
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        if exc.status_code == 401: return redirect(request, '/login')
        return HTMLResponse(views.env.get_template('error.html').render(message=exc.detail, code=exc.status_code), status_code=exc.status_code)

    @app.exception_handler(ValueError)
    async def validation_error(request, exc):
        return HTMLResponse(views.env.get_template('error.html').render(message=str(exc), code=400), status_code=400)

    @app.exception_handler(IntegrityError)
    async def conflict(request, exc):
        return HTMLResponse(views.env.get_template('error.html').render(message='Dieser Vorgang steht im Konflikt mit gespeicherten Daten. Bitte neu laden; es wurde nichts doppelt gebucht.', code=409), status_code=409)

    @app.get('/health')
    def health():
        with Session(app.state.engine) as db: db.execute(text('SELECT 1'))
        return {'status': 'ok', 'version': '0.1.0'}

    @app.get('/setup')
    def setup_page(request: Request):
        with Session(app.state.engine) as db:
            if db.scalar(select(func.count()).select_from(User)): return redirect(request, '/login')
        return render(request, 'auth.html', setup=True)

    @app.post('/setup')
    async def setup(request: Request):
        data = await request.form(); csrf(request, data)
        with transaction(app.state.engine) as db:
            if db.scalar(select(func.count()).select_from(User)): raise HTTPException(409, 'Einrichtung bereits abgeschlossen.')
            if not config.setup_token or not secrets.compare_digest(data.get('token', ''), config.setup_token):
                raise HTTPException(403, 'Invalid setup token.')
            name = data.get('name', '').strip(); company = data.get('company', '').strip()
            address = data.get('address', '').strip()
            if not name or not company or not address: raise ValueError('Name, Firma und Firmenanschrift sind erforderlich.')
            user = User(name=name, email=email(data.get('email', '')), password=password_hash(data.get('password', '')), role='admin')
            db.add(user); db.flush()
            db.add(Setting(key='company', value={'name': company, 'address': address, 'email': user.email,
                'tax_id': data.get('tax_id', ''), 'iban': data.get('iban', ''), 'phone': '', 'tax_mode': data.get('tax_mode', 'regular')}))
            db.add(Setting(key='contract', value={'text': '', 'version': 1}))
            request.session.clear(); request.session.update(uid=user.id, version=user.version, csrf=secrets.token_urlsafe(32))
        return redirect(request, '/', 'RentFlow wurde eingerichtet.')

    @app.get('/login')
    def login_page(request: Request):
        with Session(app.state.engine) as db:
            if not db.scalar(select(func.count()).select_from(User)): return redirect(request, '/setup')
        return render(request, 'auth.html', setup=False)

    @app.post('/login')
    async def login(request: Request):
        data = await request.form(); csrf(request, data)
        key = hashlib.sha256((request.client.host + ':' + data.get('email', '').lower()).encode()).hexdigest()
        valid = False
        with transaction(app.state.engine) as db:
            attempt = db.get(LoginAttempt, key)
            if attempt and datetime.fromisoformat(attempt.since) < datetime.now(timezone.utc)-timedelta(minutes=15):
                attempt.count = 0; attempt.since = now()
            if attempt and attempt.count >= 10: raise HTTPException(429, 'Zu viele Anmeldeversuche. Bitte 15 Minuten warten.')
            user = db.scalar(select(User).where(User.email == data.get('email', '').strip().lower()))
            valid = bool(user and user.active and password_valid(user.password, data.get('password', '')))
            if not valid:
                if not attempt: attempt = LoginAttempt(key=key, count=0, since=now()); db.add(attempt)
                attempt.count += 1
            else:
                if attempt: db.delete(attempt)
                request.session.clear(); request.session.update(uid=user.id, version=user.version, csrf=secrets.token_urlsafe(32))
        if not valid: raise HTTPException(400, 'E-Mail-Adresse oder Passwort ist nicht korrekt.')
        return redirect(request, '/')

    @app.post('/logout')
    async def logout(request: Request):
        csrf(request, await request.form()); request.session.clear()
        return redirect(request, '/login')

    from .web import register
    register(app)
    return app
