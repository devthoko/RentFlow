import base64, copy, hashlib, io, os
from pathlib import Path
from sqlalchemy import select, func
from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image, ImageChops
from weasyprint import HTML
from weasyprint.urls import URLFetcherResponse
from .models import Document, Asset, Evidence, Job, uid, now
from . import domain as d

TITLES={'offer':'Angebot','contract':'Mietvertrag','invoice':'Rechnung','credit':'Stornorechnung','packing':'Packliste','handover':'Übergabeprotokoll','return':'Rücknahmeprotokoll','signed_offer':'Unterschriebenes Angebot','signed_contract':'Unterschriebener Mietvertrag','signed_handover':'Unterschriebenes Übergabeprotokoll'}
env=Environment(loader=FileSystemLoader(Path(__file__).parent/'templates'),autoescape=select_autoescape())
env.filters['eur']=lambda c:f'{c/100:,.2f}'.replace(',','X').replace('.',',').replace('X','.')+' EUR'
env.filters['line_total']=lambda line:int((d.decimal(line['quantity'])*line['unit_cents']).quantize(d.Decimal('1'),rounding=d.ROUND_HALF_UP))

def store(config, content, extension):
    folder=config.data/'objects';folder.mkdir(parents=True,exist_ok=True)
    name=uid()+'.'+extension;temp=folder/(name+'.tmp');target=folder/name
    with temp.open('xb') as f:f.write(content);f.flush();os.fsync(f.fileno())
    os.chmod(temp,0o440);os.replace(temp,target)
    fd=os.open(folder,os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
    return name,hashlib.sha256(content).hexdigest()

def read(config,obj):
    raw=(config.data/'objects'/obj.filename).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=obj.sha256:raise d.RuleError('Prüfsummenfehler: Die gespeicherte Datei wurde verändert. Bitte Backup prüfen.')
    return raw

def safe_fetch(url,*args,**kwargs):
    if not url.startswith('data:image/'):raise ValueError('Externe Ressourcen sind in Dokumenten gesperrt.')
    header,content=url.split(',',1)
    if ';base64' not in header:raise ValueError('Nur eingebettete Bilder erlaubt.')
    return URLFetcherResponse(url,base64.b64decode(content,validate=True),{'Content-Type':header[5:].split(';')[0]})
safe_fetch._fail_on_errors=True

def image_data(config,asset):
    return 'data:'+asset.mime+';base64,'+base64.b64encode(read(config,asset)).decode()

def create(db,config,actor,order,kind,snapshot,number=None):
    snapshot=copy.deepcopy(snapshot);version=(db.scalar(select(func.max(Document.version)).where(Document.order_id==order.id,Document.kind==kind)) or 0)+1
    stamp=now();snapshot.update(document_kind=kind,document_version=version,document_number=number or order.number,issued_at=stamp)
    company=snapshot.get('company',{})
    if company.get('logo_id'):
        asset=db.get(Asset,company['logo_id'])
        if asset:snapshot['logo']=image_data(config,asset)
    content=env.get_template('pdf.html').render(doc=snapshot,title=TITLES.get(kind,kind))
    raw=HTML(string=content,url_fetcher=safe_fetch).write_pdf()
    filename,digest=store(config,raw,'pdf')
    obj=Document(order_id=order.id,kind=kind,version=version,number=number,snapshot=snapshot,sha256=digest,filename=filename,created_at=stamp,actor_id=actor.id)
    db.add(obj);db.flush()
    db.add(Job(kind='webdav',document_id=obj.id,payload={}))
    d.audit(db,actor,'document.created',{'document_id':obj.id,'kind':kind,'version':version,'sha256':digest},order)
    return obj

def asset(db,config,raw,name,order_id=None,pdf=False,signature=False):
    if not raw or len(raw)>10*1024*1024:raise d.RuleError('Dateien müssen zwischen 1 Byte und 10 MB groß sein.')
    if pdf:
        from pypdf import PdfReader
        if not raw.startswith(b'%PDF-'):raise d.RuleError('Bitte eine gültige PDF-Datei hochladen.')
        try:
            reader=PdfReader(io.BytesIO(raw),strict=True)
            if reader.is_encrypted or len(reader.pages)<1 or len(reader.pages)>200:raise ValueError()
            if '/JavaScript' in repr(reader.trailer) or '/JS' in repr(reader.trailer):raise ValueError()
        except Exception:raise d.RuleError('Die PDF-Datei ist beschädigt, verschlüsselt oder nicht zulässig.')
        extension,mime='pdf','application/pdf'
    else:
        try:
            Image.MAX_IMAGE_PIXELS=20000000
            image=Image.open(io.BytesIO(raw));image.verify()
            image=Image.open(io.BytesIO(raw))
            if image.width*image.height>20000000:raise ValueError()
            image.thumbnail((2000,2000));rgba=image.convert('RGBA')
            white=Image.new('RGBA',rgba.size,'white');white.alpha_composite(rgba);image=white.convert('RGB')
            if signature:
                diff=ImageChops.difference(image,Image.new('RGB',image.size,'white')).convert('L')
                if not diff.getbbox() or sum(diff.histogram()[31:])<20:raise ValueError()
            output=io.BytesIO();image.save(output,'PNG');raw=output.getvalue()
        except Exception:raise d.RuleError('Bitte ein gültiges Bild bzw. eine sichtbare Unterschrift hochladen.')
        extension,mime='png','image/png'
    filename,digest=store(config,raw,extension)
    obj=Asset(order_id=order_id,filename=filename,original_name=Path(name).name[:200],mime=mime,sha256=digest)
    db.add(obj);db.flush();db.add(Job(kind='webdav',asset_id=obj.id,payload={}))
    return obj

def sign(db,config,actor,order,document,raw,name,signer,method,consent):
    if order.closed_at:raise d.RuleError('Der Auftrag ist abgeschlossen.')
    current={'offer':order.offer_id,'contract':order.contract_id,'handover':order.handover_id}
    if document.kind not in current or current[document.kind]!=document.id:raise d.RuleError('Nur die aktuelle Dokumentversion kann unterschrieben werden.')
    if d.signed(db,document.id):return db.scalar(select(Evidence).where(Evidence.document_id==document.id))
    if document.kind=='handover':d.handover_gate(db,order)
    signer=d.required(signer,'Name der unterzeichnenden Person')
    if not consent:raise d.RuleError('Bitte die Zuordnung der Unterschrift zum Dokument bestätigen.')
    proof=asset(db,config,raw,name,order.id,pdf=method=='upload',signature=method=='digital')
    signed_document=None
    if method=='digital':
        snapshot=copy.deepcopy(document.snapshot)
        snapshot['signature']={'image':image_data(config,proof),'signer':signer,'time':now(),'original_sha256':document.sha256,'document_id':document.id}
        signed_document=create(db,config,actor,order,'signed_'+document.kind,snapshot)
    evidence=Evidence(document_id=document.id,asset_id=proof.id,signed_document_id=signed_document.id if signed_document else None,signer=signer,method=method,actor_id=actor.id)
    db.add(evidence);db.flush();d.audit(db,actor,'document.signed',{'document_id':document.id,'evidence_id':evidence.id,'method':method,'signer':signer,'document_sha256':document.sha256},order)
    return evidence
