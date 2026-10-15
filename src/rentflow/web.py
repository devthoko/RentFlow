import json, hashlib
from fastapi import Request, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from .main import render, require_user, csrf, redirect
from .db import transaction
from .models import *
from . import domain as d

def order_rows(db, query=''):
    rows=[]
    for order in db.scalars(select(Order).order_by(Order.id.desc())).all():
        customer=db.get(Customer,order.customer_id)
        if query and query.lower() not in (order.number+' '+customer.name+' '+order.event.get('name','')).lower(): continue
        rows.append({'order':order,'customer':customer,'state':d.workflow(db,order)})
    return rows

def idempotent(db, actor, key, scope, data, fn):
    if not key or len(key)<16 or len(key)>200: raise d.RuleError('Der Vorgangsschlüssel fehlt. Bitte Seite neu laden.')
    clean={k:v for k,v in data.items() if k not in ['csrf','op_key']}
    fingerprint=hashlib.sha256(json.dumps({'user':actor.id,'scope':scope,'data':clean},sort_keys=True,default=str).encode()).hexdigest()
    previous=db.get(Operation,key)
    if previous:
        if previous.fingerprint!=fingerprint: raise HTTPException(409,'Dieser Vorgangsschlüssel wurde bereits für andere Daten verwendet.')
        return previous.result
    result=fn()
    db.add(Operation(key=key,fingerprint=fingerprint,result=result));db.flush()
    return result

def register(app):
    @app.get('/')
    def dashboard(request:Request):
        with Session(app.state.engine) as db:
            require_user(request,db); rows=order_rows(db)
            stats={'open':sum(not x['order'].closed_at for x in rows),'signatures':sum('unterschrieben' in x['state']['label'] for x in rows),'due':sum(x['state']['outstanding'] or 0 for x in rows),'returns':sum(bool(x['order'].handed_at and not x['order'].returned_at) for x in rows)}
        return render(request,'dashboard.html',orders=[r for r in rows if not r['order'].closed_at],stats=stats)

    @app.get('/customers')
    def customers(request:Request,q:str=''):
        with Session(app.state.engine) as db:
            require_user(request,db)
            rows=db.scalars(select(Customer).where(Customer.name.ilike('%'+q+'%') | Customer.email.ilike('%'+q+'%')).order_by(Customer.name)).all()
        return render(request,'customers.html',customers=rows,customer=None,orders=[],q=q)

    @app.get('/customers/{customer_id}')
    def customer(request:Request,customer_id:int):
        with Session(app.state.engine) as db:
            require_user(request,db);obj=db.get(Customer,customer_id)
            if not obj:raise HTTPException(404,'Kunde nicht gefunden.')
            rows=[r for r in order_rows(db) if r['order'].customer_id==customer_id]
        return render(request,'customers.html',customers=[],customer=obj,orders=rows,q='')

    @app.post('/customers')
    @app.post('/customers/{customer_id}')
    async def customer_save(request:Request,customer_id:int|None=None):
        data=dict(await request.form());csrf(request,data)
        with transaction(app.state.engine) as db:
            actor=require_user(request,db);obj=d.customer_save(db,actor,data,customer_id)
        return redirect(request,f'/customers/{obj.id}','Kunde gespeichert.')

    @app.get('/items')
    def items(request:Request,edit:int=0,q:str=''):
        with Session(app.state.engine) as db:
            require_user(request,db);rows=db.scalars(select(Item).where(Item.name.ilike('%'+q+'%')|Item.sku.ilike('%'+q+'%')).order_by(Item.name)).all()
            packages=db.scalars(select(Package).order_by(Package.name)).all();obj=db.get(Item,edit) if edit else None
        return render(request,'items.html',items=rows,packages=packages,item=obj,q=q)

    @app.post('/items')
    async def save_item(request:Request):
        data=dict(await request.form());csrf(request,data)
        with transaction(app.state.engine) as db:
            actor=require_user(request,db);obj=d.item_save(db,actor,data,int(data['id']) if data.get('id') else None)
        return redirect(request,'/items','Artikel gespeichert.')

    @app.post('/packages')
    async def save_package(request:Request):
        data=dict(await request.form());csrf(request,data)
        data['components']={k[5:]:v for k,v in data.items() if k.startswith('part_')}
        with transaction(app.state.engine) as db:d.package_save(db,require_user(request,db),data)
        return redirect(request,'/items','Paket gespeichert.')

    @app.get('/orders')
    def orders(request:Request,q:str=''):
        with Session(app.state.engine) as db:require_user(request,db);rows=order_rows(db,q)
        return render(request,'orders.html',orders=rows,q=q)

    @app.get('/orders/new')
    def new_order_page(request:Request,q:str=''):
        with Session(app.state.engine) as db:
            require_user(request,db);customers=db.scalars(select(Customer).where(Customer.name.ilike('%'+q+'%')|Customer.email.ilike('%'+q+'%')).order_by(Customer.name)).all()
        return render(request,'new_order.html',customers=customers,q=q)

    @app.post('/orders')
    async def new_order(request:Request):
        data=dict(await request.form());csrf(request,data)
        with transaction(app.state.engine) as db:
            actor=require_user(request,db)
            def create():
                customer_id=int(data['customer_id']) if data.get('customer_id') else d.customer_save(db,actor,data).id
                obj=d.new_order(db,actor,customer_id);return {'id':obj.id}
            result=idempotent(db,actor,data.get('op_key'),'order.create',data,create)
        return redirect(request,f"/orders/{result['id']}?step=2",'Auftrag gespeichert.')

    @app.get('/orders/{order_id}')
    def order_page(request:Request,order_id:int,step:int=0):
        with Session(app.state.engine) as db:
            require_user(request,db);order=db.get(Order,order_id)
            if not order:raise HTTPException(404,'Auftrag nicht gefunden.')
            state=d.workflow(db,order);customer=db.get(Customer,order.customer_id)
            docs=db.scalars(select(Document).where(Document.order_id==order.id).order_by(Document.created_at.desc())).all()
            context={'order':order,'customer':customer,'state':state,'step':step or state['step'],'totals':d.totals(order.lines),
            'items':db.scalars(select(Item).order_by(Item.name)).all(),'packages':db.scalars(select(Package)).all(),
            'docs':docs,'evidence':{e.document_id:e for e in db.scalars(select(Evidence)).all()},
            'payments':db.scalars(select(Payment).where(Payment.invoice_id==order.invoice_id)).all() if order.invoice_id else [],
            'deposit':d.deposit_balance(db,order),'deposits':db.scalars(select(Deposit).where(Deposit.order_id==order.id)).all(),
            'physical':d.physical(order.lines),'today':d.today().isoformat(),
            'audit':db.scalars(select(Audit).where(Audit.order_id==order.id).order_by(Audit.id.desc())).all()}
        return render(request,'order.html',**context)

    @app.post('/orders/{order_id}/{action}')
    @app.post('/api/orders/{order_id}/{action}')
    async def order_action(request:Request,order_id:int,action:str):
        data=await request.json() if request.headers.get('content-type','').startswith('application/json') else dict(await request.form())
        csrf(request,data)
        with transaction(app.state.engine) as db:
            actor=require_user(request,db);order=db.get(Order,order_id)
            if not order:raise HTTPException(404,'Auftrag nicht gefunden.')
            def perform():
                if order.closed_at:raise d.RuleError('Der Auftrag ist abgeschlossen.')
                if action in ['event','line','remove-line']:
                    if str(order.revision)!=str(data.get('revision')):raise HTTPException(409,'Der Auftrag wurde zwischenzeitlich geändert. Bitte neu laden.')
                    if action=='event':d.event_save(db,actor,order,data)
                    elif action=='line':d.add_line(db,actor,order,data)
                    else:
                        d.touch(order);order.lines=[line for line in order.lines if line['id']!=data.get('line_id')]
                        d.audit(db,actor,'order.line_removed',order=order)
                else:
                    from .lifecycle import execute
                    execute(db,app.state.config,actor,order,action,data)
                db.flush()
                return {'id':order.id,'step':d.workflow(db,order)['step']}
            result=idempotent(db,actor,data.get('op_key'),'order.'+str(order.id)+'.'+action,data,perform)
        if request.url.path.startswith('/api/'):return result
        return redirect(request,f"/orders/{order_id}?step={data.get('next_step',result['step'])}",'Vorgang gespeichert.')
