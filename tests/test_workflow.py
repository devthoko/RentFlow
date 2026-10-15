import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from rentflow.models import *
from rentflow.db import transaction
from rentflow import domain as d,lifecycle as life,fulfilment as f
from rentflow.web import idempotent
from test_documents import offered,contracted,sign_doc
from conftest import token

@pytest.fixture
def invoiced(contracted,app):
    with transaction(app.state.engine) as db:
        actor=db.scalar(select(User));order=db.get(Order,contracted)
        life.invoice(db,app.state.config,actor,order,{})
    return contracted

def pay(db,app,actor,order,amount):
    life.payment(db,app.state.config,actor,order,{'amount':amount,'date':d.today().isoformat(),'method':'bank','actual':'on'})

def protocol(order,returned=False,quantity='8'):
    items=order.handover['items'] if returned else d.physical(order.lines)
    data={'time':d.today().isoformat()+'T10:00','people':'Test Mitarbeiter / Test Kunde'}
    for item in items:
        data['qty_'+item['key']]=quantity;data['condition_'+item['key']]='Gebrauchsfähig'
    return data

def test_partial_payment_and_packing(invoiced,app):
    with transaction(app.state.engine) as db:
        actor=db.scalar(select(User));order=db.get(Order,invoiced)
        assert d.outstanding(db,order)==11900
        pay(db,app,actor,order,'50')
        assert d.outstanding(db,order)==6900
        life.packing(db,app.state.config,actor,order,{})
        assert order.packing_id
        with pytest.raises(d.RuleError):f.handover_start(db,app.state.config,actor,order,{})
        f.deposit(db,app.state.config,actor,order,{'kind':'received','amount':'100','date':d.today().isoformat(),'actual':'on'})
        assert d.outstanding(db,order)==6900
        pay(db,app,actor,order,'69')
        f.handover_start(db,app.state.config,actor,order,{})
        assert order.handover

def test_direct_api_gate_for_admin_and_employee(invoiced,admin,app):
    csrf=token(admin,f'/orders/{invoiced}')
    for role in ['admin','employee']:
        with transaction(app.state.engine) as db:
            user=db.scalar(select(User));user.role=role
        result=admin.post(f'/api/orders/{invoiced}/handover-start',json={'op_key':str(uuid.uuid4()),'csrf':csrf})
        assert result.status_code==400
        assert 'offen' in result.text

def test_handover_rechecks_payment_at_completion(invoiced,app):
    with transaction(app.state.engine) as db:
        actor=db.scalar(select(User));order=db.get(Order,invoiced)
        pay(db,app,actor,order,'119')
        f.handover_save(db,app.state.config,actor,order,protocol(order))
        with pytest.raises(d.RuleError):f.handover_complete(db,app.state.config,actor,order,{'document_id':order.handover_id})
        sign_doc(db,app.state.config,actor,order,order.handover_id)
        payment=db.scalar(select(Payment).where(Payment.invoice_id==order.invoice_id))
        life.reverse_payment(db,app.state.config,actor,order,{'payment_id':payment.id,'method':'correction','reason':'Falscher Eingang','date':d.today().isoformat()})
        with pytest.raises(d.RuleError):f.handover_complete(db,app.state.config,actor,order,{'document_id':order.handover_id})
        assert not order.handed_at

def test_return_actual_quantities_deposit_and_close(invoiced,app):
    with transaction(app.state.engine) as db:
        actor=db.scalar(select(User));order=db.get(Order,invoiced);pay(db,app,actor,order,'119')
        f.deposit(db,app.state.config,actor,order,{'kind':'received','amount':'100','date':d.today().isoformat(),'actual':'on'})
        f.handover_save(db,app.state.config,actor,order,protocol(order,quantity='8'))
        sign_doc(db,app.state.config,actor,order,order.handover_id)
        f.handover_complete(db,app.state.config,actor,order,{'document_id':order.handover_id})
        data=protocol(order,True,'7');key=order.handover['items'][0]['key']
        data.update({'issue_'+key:'missing','cost_'+key:'20','costs_confirmed':'on'})
        f.return_complete(db,app.state.config,actor,order,data)
        assert order.returned['items'][0]['missing']=='1'
        assert order.returned['items'][0]['quantity']=='8'
        assert not d.signed(db,order.return_id)
        with pytest.raises(d.RuleError):f.close(db,app.state.config,actor,order,{})
        with pytest.raises(d.RuleError):f.deposit(db,app.state.config,actor,order,{'kind':'retained','amount':'20','date':d.today().isoformat()})
        f.deposit(db,app.state.config,actor,order,{'kind':'retained','amount':'20','reason':'Fehlmenge laut Rücknahme','date':d.today().isoformat()})
        f.deposit(db,app.state.config,actor,order,{'kind':'refunded','amount':'80','date':d.today().isoformat(),'actual':'on'})
        f.close(db,app.state.config,actor,order,{})
        assert d.workflow(db,order)['label']=='Auftrag abgeschlossen'
        assert d.deposit_balance(db,order)['remaining']==0

def test_parallel_duplicate_payments(invoiced,app):
    key=str(uuid.uuid4())
    def run():
        with transaction(app.state.engine) as db:
            actor=db.scalar(select(User));order=db.get(Order,invoiced)
            def perform():pay(db,app,actor,order,'50');return {'ok':True}
            return idempotent(db,actor,key,'payment',{'amount':'50'},perform)
    with ThreadPoolExecutor(max_workers=2) as pool:assert list(pool.map(lambda _:run(),range(2)))==[{'ok':True}]*2
    with Session(app.state.engine) as db:
        order=db.get(Order,invoiced)
        assert db.scalar(select(func.count()).select_from(Payment))==1
        assert d.outstanding(db,order)==6900

def test_parallel_invoice_creation(contracted,app):
    def run():
        with transaction(app.state.engine) as db:
            actor=db.scalar(select(User));order=db.get(Order,contracted)
            life.invoice(db,app.state.config,actor,order,{})
            return order.invoice_id
    with ThreadPoolExecutor(max_workers=2) as pool:ids=list(pool.map(lambda _:run(),range(2)))
    assert len(set(ids))==1
    with Session(app.state.engine) as db:assert db.scalar(select(func.count()).select_from(Document).where(Document.kind=='invoice'))==1

def test_invoice_correction_preserves_original(invoiced,app):
    with transaction(app.state.engine) as db:
        actor=db.scalar(select(User));order=db.get(Order,invoiced);old=order.invoice_id
        with pytest.raises(d.RuleError):d.add_line(db,actor,order,{'name':'Extra','price':'1'})
        life.cancel_invoice(db,app.state.config,actor,order,{'reason':'Leistungsänderung'})
        assert order.invoice_id is None and db.get(Document,old)
        credit=db.scalar(select(Document).where(Document.kind=='credit'))
        assert credit.snapshot['cancelled_id']==old
        life.invoice(db,app.state.config,actor,order,{})
        assert order.invoice_id!=old

def test_unannounced_future_or_negative_payments_rejected(invoiced,app):
    with transaction(app.state.engine) as db:
        actor=db.scalar(select(User));order=db.get(Order,invoiced)
        for data in [{'amount':'-1','actual':'on'},{'amount':'5'},{'amount':'5','actual':'on','date':'2999-01-01'}]:
            with pytest.raises(d.RuleError):life.payment(db,app.state.config,actor,order,{'date':d.today().isoformat(),'method':'bank',**data})
        assert d.outstanding(db,order)==11900

def test_all_workflow_pages_render(invoiced,admin):
    for step in range(1,10):
        result=admin.get(f'/orders/{invoiced}?step={step}')
        assert result.status_code==200,result.text
