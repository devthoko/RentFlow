import base64, binascii
from fastapi import Request, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from .main import require_user,render,redirect,csrf
from .db import transaction
from .models import *
from . import domain as d
from . import documents as docs

def register(app):
    @app.get('/documents/{document_id}')
    def document_page(request:Request,document_id:str):
        with Session(app.state.engine) as db:
            require_user(request,db);obj=db.get(Document,document_id)
            if not obj:raise HTTPException(404,'Dokument nicht gefunden.')
            order=db.get(Order,obj.order_id);proof=db.scalar(select(Evidence).where(Evidence.document_id==obj.id))
            jobs=db.scalars(select(Job).where(Job.document_id==obj.id).order_by(Job.created_at.desc())).all()
            can_sign=obj.kind in ['offer','contract','handover'] and getattr(order,obj.kind+'_id')==obj.id and not proof and not order.closed_at
        return render(request,'document.html',doc=obj,order=order,proof=proof,jobs=jobs,title=docs.TITLES.get(obj.kind,obj.kind),can_sign=can_sign)

    @app.get('/documents/{document_id}/file')
    def document_file(request:Request,document_id:str,download:int=0):
        with Session(app.state.engine) as db:
            require_user(request,db);obj=db.get(Document,document_id)
            if not obj:raise HTTPException(404,'Dokument nicht gefunden.')
            raw=docs.read(app.state.config,obj);name=(obj.number or obj.kind)+'-v'+str(obj.version)+'.pdf'
        return Response(raw,media_type='application/pdf',headers={'Content-Disposition':('attachment' if download else 'inline')+'; filename="'+name+'"'})

    @app.get('/assets/{asset_id}')
    def asset_file(request:Request,asset_id:str):
        with Session(app.state.engine) as db:
            require_user(request,db);obj=db.get(Asset,asset_id)
            if not obj:raise HTTPException(404,'Datei nicht gefunden.')
            raw=docs.read(app.state.config,obj)
        return Response(raw,media_type=obj.mime,headers={'Content-Disposition':'inline; filename="'+obj.id+('.pdf' if obj.mime=='application/pdf' else '.png')+'"'})

    @app.post('/documents/{document_id}/sign')
    async def sign(request:Request,document_id:str):
        form=await request.form();csrf(request,form)
        method=form.get('method');raw=b'';name='unterschrift.png'
        if method=='digital':
            try:
                value=form.get('signature','')
                if not value.startswith('data:image/png;base64,'):raise ValueError()
                raw=base64.b64decode(value.split(',',1)[1],validate=True)
            except (ValueError,binascii.Error):raise d.RuleError('Bitte eine gültige Unterschrift zeichnen.')
        elif method=='upload':
            upload=form.get('file')
            if not upload or not hasattr(upload,'read'):raise d.RuleError('Bitte ein unterschriebenes PDF auswählen.')
            raw=await upload.read(10*1024*1024+1);name=upload.filename
        else:raise d.RuleError('Ungültige Unterschriftsart.')
        with transaction(app.state.engine) as db:
            actor=require_user(request,db);obj=db.get(Document,document_id)
            if not obj:raise HTTPException(404,'Dokument nicht gefunden.')
            order=db.get(Order,obj.order_id)
            docs.sign(db,app.state.config,actor,order,obj,raw,name,form.get('signer',''),method,form.get('consent')=='on')
        return redirect(request,'/documents/'+document_id,'Unterschriftsnachweis gespeichert.')

    @app.post('/items/{item_id}/image')
    async def item_image(request:Request,item_id:int):
        form=await request.form();csrf(request,form);upload=form.get('file')
        if not upload or not hasattr(upload,'read'):raise d.RuleError('Bitte ein Bild auswählen.')
        raw=await upload.read(10*1024*1024+1)
        with transaction(app.state.engine) as db:
            actor=require_user(request,db);item=db.get(Item,item_id)
            if not item:raise HTTPException(404,'Artikel nicht gefunden.')
            item.image_id=docs.asset(db,app.state.config,raw,upload.filename).id
            d.audit(db,actor,'item.image_uploaded',{'item_id':item.id})
        return redirect(request,'/items?edit='+str(item_id),'Artikelbild gespeichert.')

    @app.post('/orders/{order_id}/photo')
    async def photo_upload(request:Request,order_id:int):
        form=await request.form();csrf(request,form);upload=form.get('file')
        if not upload or not hasattr(upload,'read'):raise d.RuleError('Bitte ein Foto auswählen.')
        raw=await upload.read(10*1024*1024+1)
        with transaction(app.state.engine) as db:
            actor=require_user(request,db);order=db.get(Order,order_id)
            if not order or order.closed_at:raise d.RuleError('Dieser Auftrag kann nicht mehr bearbeitet werden.')
            obj=docs.asset(db,app.state.config,raw,upload.filename,order.id)
            d.audit(db,actor,'photo.uploaded',{'asset_id':obj.id},order)
            result={'id':obj.id,'url':'/assets/'+obj.id}
        return result
