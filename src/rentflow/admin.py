from fastapi import Request,HTTPException
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from .main import require_user,render,redirect,csrf
from .db import transaction
from .models import *
from .security import password_hash,email,encrypt
from . import domain as d
from . import documents as docs

def register(app):
    @app.get('/settings')
    def settings(request:Request):
        with Session(app.state.engine) as db:
            require_user(request,db,True)
            company=d.setting(db,'company');contract=d.setting(db,'contract')
            smtp=d.setting(db,'smtp');webdav=d.setting(db,'webdav')
            smtp.pop('password',None);webdav.pop('password',None)
            users=db.scalars(select(User).order_by(User.id)).all()
            jobs=db.scalars(select(Job).order_by(Job.created_at.desc()).limit(30)).all()
        return render(request,'settings.html',company=company,contract=contract,smtp=smtp,webdav=webdav,users=users,jobs=jobs)

    @app.post('/settings/{section}')
    async def save_settings(request:Request,section:str):
        form=await request.form();csrf(request,form);data=dict(form)
        with transaction(app.state.engine) as db:
            actor=require_user(request,db,True)
            if section=='company':
                company={key:str(data.get(key,'')).strip() for key in ['name','address','email','phone','tax_id','iban','street','postcode','city','country','tax_mode']}
                d.required(company['name'],'Firmenname');d.required(company['address'],'Firmenanschrift');company['email']=email(company['email'])
                if company['tax_mode'] not in ['regular','small']:raise d.RuleError('Ungültige Besteuerungsart.')
                old=d.setting(db,'company');company['logo_id']=old.get('logo_id')
                d.set_setting(db,'company',company)
            elif section=='contract':
                old=d.setting(db,'contract')
                d.set_setting(db,'contract',{'text':d.required(data.get('text'),'Vertragstext'),'version':old.get('version',0)+1})
            elif section=='user':
                obj=db.get(User,int(data['id'])) if data.get('id') else User()
                if not obj:raise d.RuleError('Benutzer nicht gefunden.')
                role=data.get('role')
                if role not in ['admin','employee']:raise d.RuleError('Ungültige Rolle.')
                active=data.get('active')=='on'
                if obj.id and obj.role=='admin' and obj.active and (role!='admin' or not active):
                    count=db.scalar(select(func.count()).select_from(User).where(User.role=='admin',User.active==True))
                    if count<=1:raise d.RuleError('Mindestens ein aktiver Administrator muss erhalten bleiben.')
                obj.name=d.required(data.get('name'),'Name');obj.email=email(data.get('email',''));obj.role=role;obj.active=active
                if data.get('password'):obj.password=password_hash(data['password'])
                elif not obj.id:raise d.RuleError('Ein Passwort ist erforderlich.')
                obj.version=(obj.version or 0)+1;db.add(obj);db.flush()
                if obj.id==actor.id:request.session['version']=obj.version
            elif section=='smtp':
                old=d.setting(db,'smtp')
                mode=data.get('mode','starttls')
                if mode not in ['starttls','ssl']:raise d.RuleError('SMTP benötigt STARTTLS oder TLS.')
                try:port=int(data.get('port','587'))
                except ValueError:raise d.RuleError('Ungültiger SMTP-Port.')
                if not 1<=port<=65535:raise d.RuleError('Ungültiger SMTP-Port.')
                d.set_setting(db,'smtp',{'host':d.required(data.get('host'),'SMTP-Host'),'port':port,'mode':mode,'username':data.get('username',''),
                'password':encrypt(app.state.config,data['password']) if data.get('password') else old.get('password',''),
                'sender_name':d.required(data.get('sender_name'),'Absendername'),'sender':email(data.get('sender',''))})
            elif section=='webdav':
                from urllib.parse import urlsplit
                url=d.required(data.get('url'),'WebDAV-Adresse').rstrip('/')
                parsed=urlsplit(url)
                if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                    raise d.RuleError('Bitte eine HTTPS-WebDAV-Adresse ohne eingebettete Zugangsdaten angeben.')
                old=d.setting(db,'webdav')
                d.set_setting(db,'webdav',{'url':url,'username':d.required(data.get('username'),'Benutzername'),
                'password':encrypt(app.state.config,data['password']) if data.get('password') else old.get('password','')})
            else:raise HTTPException(404,'Einstellung nicht gefunden.')
            d.audit(db,actor,'settings.'+section,{'section':section})
        return redirect(request,'/settings','Einstellungen gespeichert.')

    @app.post('/settings-logo')
    async def logo(request:Request):
        form=await request.form();csrf(request,form);upload=form.get('file')
        if not upload or not hasattr(upload,'read'):raise d.RuleError('Bitte ein Logo auswählen.')
        raw=await upload.read(10*1024*1024+1)
        with transaction(app.state.engine) as db:
            actor=require_user(request,db,True);obj=docs.asset(db,app.state.config,raw,upload.filename)
            company=d.setting(db,'company');company['logo_id']=obj.id;d.set_setting(db,'company',company)
            d.audit(db,actor,'company.logo_uploaded',{'asset_id':obj.id})
        return redirect(request,'/settings','Logo gespeichert.')
