import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Boolean, JSON, ForeignKey, UniqueConstraint, CheckConstraint
from .db import Base

def uid(): return str(uuid.uuid4())
def now(): return datetime.now(timezone.utc).isoformat()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    role = Column(String, nullable=False, default='employee')
    active = Column(Boolean, default=True, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    __table_args__ = (CheckConstraint("role IN ('admin','employee')"),)

class Setting(Base):
    __tablename__ = 'settings'
    key = Column(String, primary_key=True)
    value = Column(JSON, nullable=False)

class Customer(Base):
    __tablename__ = 'customers'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    phone = Column(String, default='')
    address = Column(Text, default='')
    contact = Column(String, default='')
    notes = Column(Text, default='')
    business = Column(Boolean, default=False)
    routing_id = Column(String, default='')

class Item(Base):
    __tablename__ = 'items'
    id = Column(Integer, primary_key=True)
    sku = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    category = Column(String, default='')
    description = Column(Text, default='')
    cents = Column(Integer, nullable=False)
    tax = Column(String, nullable=False, default='19')
    replacement_cents = Column(Integer, default=0)
    image_id = Column(String, ForeignKey('assets.id'), nullable=True)
    active = Column(Boolean, default=True)
    __table_args__ = (CheckConstraint('cents >= 0 AND replacement_cents >= 0'),)

class Package(Base):
    __tablename__ = 'packages'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text, default='')
    cents = Column(Integer, nullable=False)
    tax = Column(String, default='19')
    components = Column(JSON, nullable=False)

class Order(Base):
    __tablename__ = 'orders'
    id = Column(Integer, primary_key=True)
    number = Column(String, unique=True, nullable=False)
    customer_id = Column(Integer, ForeignKey('customers.id'), nullable=False)
    event = Column(JSON, nullable=False, default=dict)
    lines = Column(JSON, nullable=False, default=list)
    revision = Column(Integer, nullable=False, default=1)
    offer_id = Column(String, ForeignKey('documents.id', use_alter=True), nullable=True)
    contract_id = Column(String, ForeignKey('documents.id', use_alter=True), nullable=True)
    invoice_id = Column(String, ForeignKey('documents.id', use_alter=True), nullable=True)
    packing_id = Column(String, ForeignKey('documents.id', use_alter=True), nullable=True)
    handover_id = Column(String, ForeignKey('documents.id', use_alter=True), nullable=True)
    return_id = Column(String, ForeignKey('documents.id', use_alter=True), nullable=True)
    handover = Column(JSON, nullable=False, default=dict)
    returned = Column(JSON, nullable=False, default=dict)
    handed_at = Column(String, nullable=True)
    returned_at = Column(String, nullable=True)
    closed_at = Column(String, nullable=True)
    deposit_cents = Column(Integer, default=0, nullable=False)
    created_at = Column(String, default=now, nullable=False)
    __table_args__ = (CheckConstraint('deposit_cents >= 0'),)

class Document(Base):
    __tablename__ = 'documents'
    id = Column(String, primary_key=True, default=uid)
    order_id = Column(Integer, ForeignKey('orders.id'), nullable=False)
    kind = Column(String, nullable=False)
    version = Column(Integer, nullable=False)
    number = Column(String, unique=True, nullable=True)
    snapshot = Column(JSON, nullable=False)
    sha256 = Column(String, nullable=False)
    filename = Column(String, nullable=False, unique=True)
    created_at = Column(String, default=now, nullable=False)
    actor_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    __table_args__ = (UniqueConstraint('order_id', 'kind', 'version'),)

class Evidence(Base):
    __tablename__ = 'evidence'
    id = Column(String, primary_key=True, default=uid)
    document_id = Column(String, ForeignKey('documents.id'), nullable=False, unique=True)
    asset_id = Column(String, ForeignKey('assets.id'), nullable=False)
    signed_document_id = Column(String, ForeignKey('documents.id'), nullable=True)
    signer = Column(String, nullable=False)
    method = Column(String, nullable=False)
    created_at = Column(String, default=now, nullable=False)
    actor_id = Column(Integer, ForeignKey('users.id'), nullable=False)

class Asset(Base):
    __tablename__ = 'assets'
    id = Column(String, primary_key=True, default=uid)
    order_id = Column(Integer, ForeignKey('orders.id'), nullable=True)
    filename = Column(String, nullable=False, unique=True)
    original_name = Column(String, nullable=False)
    mime = Column(String, nullable=False)
    sha256 = Column(String, nullable=False)
    created_at = Column(String, default=now, nullable=False)

class Payment(Base):
    __tablename__ = 'payments'
    id = Column(String, primary_key=True, default=uid)
    invoice_id = Column(String, ForeignKey('documents.id'), nullable=False)
    cents = Column(Integer, nullable=False)
    date = Column(String, nullable=False)
    method = Column(String, nullable=False)
    reference = Column(Text, default='')
    reversal_of = Column(String, ForeignKey('payments.id'), unique=True, nullable=True)
    actor_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    created_at = Column(String, default=now)
    __table_args__ = (CheckConstraint('cents != 0'),)

class Deposit(Base):
    __tablename__ = 'deposits'
    id = Column(String, primary_key=True, default=uid)
    order_id = Column(Integer, ForeignKey('orders.id'), nullable=False)
    kind = Column(String, nullable=False)
    cents = Column(Integer, nullable=False)
    date = Column(String, nullable=False)
    reason = Column(Text, default='')
    actor_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    created_at = Column(String, default=now)
    __table_args__ = (CheckConstraint('cents > 0'), CheckConstraint("kind IN ('received','refunded','retained')"))

class Audit(Base):
    __tablename__ = 'audit'
    id = Column(Integer, primary_key=True)
    actor_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    order_id = Column(Integer, ForeignKey('orders.id'), nullable=True)
    action = Column(String, nullable=False)
    detail = Column(JSON, nullable=False)
    created_at = Column(String, default=now)
    previous = Column(String, nullable=False)
    digest = Column(String, nullable=False)

class Operation(Base):
    __tablename__ = 'operations'
    key = Column(String, primary_key=True)
    fingerprint = Column(String, nullable=False)
    result = Column(JSON, nullable=False)

class Counter(Base):
    __tablename__ = 'counters'
    key = Column(String, primary_key=True)
    value = Column(Integer, default=0, nullable=False)

class Job(Base):
    __tablename__ = 'jobs'
    id = Column(String, primary_key=True, default=uid)
    kind = Column(String, nullable=False)
    document_id = Column(String, ForeignKey('documents.id'), nullable=True)
    asset_id = Column(String, ForeignKey('assets.id'), nullable=True)
    payload = Column(JSON, nullable=False, default=dict)
    status = Column(String, default='pending', nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    error = Column(Text, default='')
    next_at = Column(String, default=now, nullable=False)
    created_at = Column(String, default=now)
    finished_at = Column(String, nullable=True)

class LoginAttempt(Base):
    __tablename__ = 'login_attempts'
    key = Column(String, primary_key=True)
    count = Column(Integer, default=0)
    since = Column(String, nullable=False)
