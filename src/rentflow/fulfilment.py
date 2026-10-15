import copy
from datetime import datetime
from sqlalchemy import select
from .models import *
from . import domain as d, documents as docs

def photo_data(db,config,order,value):
    result=[]
    for asset_id in str(value or '').split(','):
        if not asset_id:continue
        asset=db.get(Asset,asset_id)
        if not asset or asset.order_id!=order.id or not asset.mime.startswith('image/'):raise d.RuleError('Ungültige Fotozuordnung.')
        result.append(docs.image_data(config,asset))
    return result

def protocol_time(value):
    try:stamp=datetime.fromisoformat(value)
    except (TypeError,ValueError):raise d.RuleError('Bitte einen gültigen Zeitpunkt angeben.')
    if stamp.date()>d.today():raise d.RuleError('Ein tatsächlicher Übergabe- oder Rücknahmezeitpunkt darf nicht in der Zukunft liegen.')
    return stamp.isoformat(timespec='minutes')

def handover_start(db,config,actor,order,data):
    d.handover_gate(db,order)
    if order.handed_at:raise d.RuleError('Die Übergabe ist bereits abgeschlossen.')
    if not order.handover:
        order.handover={'items':copy.deepcopy(db.get(Document,order.invoice_id).snapshot['physical']),'started_at':now()}
        d.audit(db,actor,'handover.started',order=order)

def handover_save(db,config,actor,order,data):
    d.handover_gate(db,order)
    if order.handed_at:raise d.RuleError('Die Übergabe ist bereits abgeschlossen.')
    rows=[]
    source=db.get(Document,order.invoice_id)
    for item in source.snapshot['physical']:
        key=item['key'];count=d.decimal(data.get('qty_'+key,item['quantity']))
        if count<0 or count>d.decimal(item['quantity']) or count!=count.quantize(d.Decimal('.001')):raise d.RuleError('Übergebene Mengen müssen zwischen 0 und der vereinbarten Menge liegen.')
        rows.append({**item,'quantity':str(count),'condition':d.required(data.get('condition_'+key),'Zustand von '+item['name']),
        'damage':str(data.get('damage_'+key,'')),'notes':str(data.get('notes_'+key,'')),'photos':photo_data(db,config,order,data.get('photos_'+key,''))})
    protocol={'items':rows,'time':protocol_time(data.get('time')),'people':d.required(data.get('people'),'Beteiligte Personen')}
    snap=copy.deepcopy(source.snapshot);snap['protocol']=protocol
    obj=docs.create(db,config,actor,order,'handover',snap)
    order.handover=protocol;order.handover_id=obj.id
    d.audit(db,actor,'handover.protocol_saved',{'document_id':obj.id},order)

def handover_complete(db,config,actor,order,data):
    d.handover_gate(db,order)
    if order.handed_at:return
    if not order.handover_id or not d.signed(db,order.handover_id):raise d.RuleError('Das aktuelle Übergabeprotokoll muss unterschrieben sein.')
    if data.get('document_id')!=order.handover_id:raise d.RuleError('Das Übergabeprotokoll wurde zwischenzeitlich geändert. Bitte neu laden.')
    order.handed_at=now()
    d.audit(db,actor,'handover.completed',{'document_id':order.handover_id},order)

def return_complete(db,config,actor,order,data):
    if not order.handed_at:raise d.RuleError('Zuerst die Übergabe abschließen.')
    if order.returned_at:return
    rows=[]
    for item in order.handover['items']:
        key=item['key'];count=d.decimal(data.get('qty_'+key,item['quantity']));handed=d.decimal(item['quantity'])
        if count<0 or count>handed or count!=count.quantize(d.Decimal('.001')):raise d.RuleError('Die Rückgabemenge muss zwischen 0 und der tatsächlich übergebenen Menge liegen.')
        cost=d.money(data.get('cost_'+key,'0'))
        issue=str(data.get('issue_'+key,''))
        if issue not in ['','damage','missing','repair','replacement','cleaning']:raise d.RuleError('Ungültige Schadensart.')
        if cost and not issue:raise d.RuleError('Bitte den Grund für die Kosten angeben.')
        if cost and str(data.get('costs_confirmed','')) not in ['on','1','true']:raise d.RuleError('Die erfassten Kosten müssen vor Abschluss bestätigt werden.')
        rows.append({**item,'photos':photo_data(db,config,order,data.get('photos_'+key,'')),'returned':str(count),'missing':str(handed-count),
        'before':item['condition'],'prior_damage':item.get('damage',''),'condition':d.required(data.get('condition_'+key),'Rücknahmezustand von '+item['name']),
        'notes':str(data.get('notes_'+key,'')),'issue':issue,'cost_cents':cost})
    stamp=protocol_time(data.get('time'))
    if datetime.fromisoformat(stamp)<datetime.fromisoformat(order.handover['time']):raise d.RuleError('Die Rücknahme darf nicht vor der dokumentierten Übergabe liegen.')
    protocol={'items':rows,'time':stamp,'people':d.required(data.get('people'),'Beteiligte Personen'),'costs_confirmed':True}
    snap=copy.deepcopy(db.get(Document,order.handover_id).snapshot);snap['protocol']=protocol;snap['handover_id']=order.handover_id
    order.return_id=docs.create(db,config,actor,order,'return',snap).id;order.returned=protocol;order.returned_at=now()
    d.audit(db,actor,'return.completed',{'document_id':order.return_id,'cost_cents':sum(row['cost_cents'] for row in rows)},order)

def deposit(db,config,actor,order,data):
    kind=data.get('kind');cents=d.money(data.get('amount','0'))
    if kind not in ['received','refunded','retained'] or cents<=0:raise d.RuleError('Bitte eine gültige Kautionsbuchung angeben.')
    reason=str(data.get('reason','')).strip()
    if kind in ['refunded','retained']:
        if not order.returned_at:raise d.RuleError('Vor der Kautionsabrechnung bitte die Rücknahme abschließen.')
        if cents>d.deposit_balance(db,order)['remaining']:raise d.RuleError('Der Betrag überschreitet die noch vorhandene Kaution.')
    if kind=='retained':d.required(reason,'Begründung des Einbehalts')
    elif str(data.get('actual','')) not in ['on','1','true']:raise d.RuleError('Bitte den tatsächlichen Geldfluss bestätigen.')
    row=Deposit(order_id=order.id,kind=kind,cents=cents,date=d.booking_date(data.get('date')),reason=reason,actor_id=actor.id)
    db.add(row);db.flush();d.audit(db,actor,'deposit.'+kind,{'id':row.id,'cents':cents,'reason':reason},order)

def close(db,config,actor,order,data):
    d.handover_gate(db,order)
    if not order.handed_at or not order.returned_at:raise d.RuleError('Übergabe und Rücknahme müssen abgeschlossen sein.')
    if d.deposit_balance(db,order)['remaining']!=0:raise d.RuleError('Die tatsächlich erhaltene Kaution ist noch nicht vollständig abgerechnet.')
    order.closed_at=now();d.audit(db,actor,'order.completed',order=order)

ACTIONS={'handover-start':handover_start,'handover-save':handover_save,'handover-complete':handover_complete,'return':return_complete,'deposit':deposit,'close':close}
