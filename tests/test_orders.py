import pytest
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from rentflow.db import transaction
from rentflow.models import User,Customer,Order,Item
from rentflow import domain as d
from conftest import token

def test_customer_independent(admin,app):
    r=admin.post('/customers',data={'csrf':token(admin,'/customers'),'name':'Kunde','email':'kunde@example.com'})
    assert r.status_code==200
    with Session(app.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(Customer))==1
        assert db.scalar(select(func.count()).select_from(Order))==0

def test_order_resume_and_lines(admin,app):
    with transaction(app.state.engine) as db:
        actor=db.scalar(select(User))
        customer=d.customer_save(db,actor,{'name':'Kunde','email':'kunde@example.com'})
        order=d.new_order(db,actor,customer.id)
        with pytest.raises(d.RuleError): d.event_save(db,actor,order,{'name':'Party'})
        d.event_save(db,actor,order,{'name':'Party','date':'2026-12-12','mode':'pickup','handover_at':'2026-12-11T12:00','return_at':'2026-12-13T12:00','deposit':'100'})
        item=d.item_save(db,actor,{'sku':'TEST-1','name':'Stuhl','price':'12,50','tax':'19'})
        d.add_line(db,actor,order,{'kind':'item','item_id':item.id,'quantity':'2'})
        d.add_line(db,actor,order,{'kind':'free','name':'Lieferung','price':'20','quantity':'1','tax':'19'})
        oid=order.id
    assert admin.get(f'/orders/{oid}').status_code==200
    with Session(app.state.engine) as db:
        order=db.get(Order,oid)
        assert len(order.lines)==2
        assert d.totals(order.lines)['gross_cents']==5355
        assert order.deposit_cents==10000
        assert d.workflow(db,order)['step']==3

def test_event_delivery_and_dates():
    with pytest.raises(d.RuleError):d.validate_event({'name':'X','date':'2026-01-02','mode':'delivery','handover_at':'2026-01-01T12:00','return_at':'2026-01-03T12:00'})
    with pytest.raises(d.RuleError):d.validate_event({'name':'X','date':'2026-01-02','mode':'pickup','handover_at':'2026-01-03T12:00','return_at':'2026-01-01T12:00'})

def test_package_components(admin,app):
    with transaction(app.state.engine) as db:
        actor=db.scalar(select(User));item=d.item_save(db,actor,{'sku':'P1','name':'Glas','price':'2'})
        package=d.package_save(db,actor,{'name':'Tafel','price':'50','components':{str(item.id):'6'}})
        customer=d.customer_save(db,actor,{'name':'K','email':'k@example.com'});order=d.new_order(db,actor,customer.id)
        d.add_line(db,actor,order,{'kind':'package','package_id':package.id,'quantity':'3'})
        assert d.physical(order.lines)[0]['quantity']=='18'
        assert d.totals(order.lines)['net_cents']==15000
