import io, hashlib
import pytest
from PIL import Image, ImageDraw
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from rentflow.db import transaction
from rentflow.models import *
from rentflow import domain as d, lifecycle as life, documents as docs


def signature():
    image = Image.new("RGB", (400, 160), "white")
    draw = ImageDraw.Draw(image)
    draw.line(
        [(20, 100), (50, 40), (80, 120), (130, 30), (160, 100), (250, 80)],
        fill="black",
        width=4,
    )
    buf = io.BytesIO()
    image.save(buf, "PNG")
    return buf.getvalue()


def prepare(db, actor):
    customer = d.customer_save(
        db,
        actor,
        {
            "name": "Test Kunde",
            "email": "kunde@example.com",
            "address": "Testweg 1, 12345 Berlin",
        },
    )
    order = d.new_order(db, actor, customer.id)
    d.event_save(
        db,
        actor,
        order,
        {
            "name": "Testevent",
            "date": "2026-12-12",
            "mode": "pickup",
            "handover_at": "2026-12-11T12:00",
            "return_at": "2026-12-13T12:00",
            "deposit": "100",
        },
    )
    item = d.item_save(
        db, actor, {"sku": uid(), "name": "Stuhl", "price": "10", "tax": "19"}
    )
    d.add_line(db, actor, order, {"kind": "item", "item_id": item.id, "quantity": "10"})
    return order


@pytest.fixture
def offered(admin, app):
    with transaction(app.state.engine) as db:
        actor = db.scalar(select(User))
        order = prepare(db, actor)
        life.offer(db, app.state.config, actor, order, {})
        oid = order.id
    return oid


def sign_doc(db, config, actor, order, docid, method="digital"):
    doc = db.get(Document, docid)
    return docs.sign(
        db,
        config,
        actor,
        order,
        doc,
        signature() if method == "digital" else docs.read(config, doc),
        "proof.png" if method == "digital" else "proof.pdf",
        "Test Kunde",
        method,
        True,
    )


@pytest.fixture
def contracted(offered, app):
    with transaction(app.state.engine) as db:
        actor = db.scalar(select(User))
        order = db.get(Order, offered)
        sign_doc(db, app.state.config, actor, order, order.offer_id)
        d.set_setting(
            db,
            "contract",
            {
                "text": "Vermietung der aufgeführten Artikel. Rückgabe zum vereinbarten Termin.",
                "version": 1,
            },
        )
        life.contract(db, app.state.config, actor, order, {})
        sign_doc(db, app.state.config, actor, order, order.contract_id)
    return offered


def test_offer_snapshot_signature_and_revision(offered, app):
    with transaction(app.state.engine) as db:
        actor = db.scalar(select(User))
        order = db.get(Order, offered)
        original = db.get(Document, order.offer_id)
        digest = original.sha256
        evidence = sign_doc(db, app.state.config, actor, order, original.id)
        assert evidence.document_id == original.id
        item = db.scalar(select(Item))
        item.cents = 99999
        assert original.snapshot["lines"][0]["unit_cents"] == 1000
        d.add_line(
            db, actor, order, {"kind": "free", "name": "Lieferung", "price": "5"}
        )
        assert order.offer_id is None
        life.offer(db, app.state.config, actor, order, {})
        assert order.offer_id != original.id and not d.signed(db, order.offer_id)
        assert original.sha256 == digest
        assert (
            hashlib.sha256(docs.read(app.state.config, original)).hexdigest() == digest
        )


def test_uploaded_signature_and_immutable_document(offered, app):
    with transaction(app.state.engine) as db:
        actor = db.scalar(select(User))
        order = db.get(Order, offered)
        evidence = sign_doc(
            db, app.state.config, actor, order, order.offer_id, "upload"
        )
        assert evidence.method == "upload"
        assert d.signed(db, order.offer_id)
    with pytest.raises(IntegrityError):
        with transaction(app.state.engine) as db:
            db.execute(text("UPDATE documents SET sha256='changed'"))


def test_contract_gate_and_template_snapshot(offered, app):
    with transaction(app.state.engine) as db:
        actor = db.scalar(select(User))
        order = db.get(Order, offered)
        with pytest.raises(d.RuleError):
            life.contract(db, app.state.config, actor, order, {})
        sign_doc(db, app.state.config, actor, order, order.offer_id)
        d.set_setting(
            db, "contract", {"text": "Vertragstext Fassung eins", "version": 1}
        )
        life.contract(db, app.state.config, actor, order, {})
        doc = db.get(Document, order.contract_id)
        d.set_setting(db, "contract", {"text": "Neue Fassung zwei", "version": 2})
        assert doc.snapshot["contract_text"] == "Vertragstext Fassung eins"
        with pytest.raises(d.RuleError):
            life.invoice(db, app.state.config, actor, order, {})


def test_bad_uploads_and_blank_signature(offered, app):
    with transaction(app.state.engine) as db:
        actor = db.scalar(select(User))
        order = db.get(Order, offered)
        doc = db.get(Document, order.offer_id)
        with pytest.raises(d.RuleError):
            docs.sign(
                db,
                app.state.config,
                actor,
                order,
                doc,
                b"not pdf",
                "x.pdf",
                "Kunde",
                "upload",
                True,
            )
        blank = Image.new("RGB", (300, 100), "white")
        buf = io.BytesIO()
        blank.save(buf, "PNG")
        with pytest.raises(d.RuleError):
            docs.sign(
                db,
                app.state.config,
                actor,
                order,
                doc,
                buf.getvalue(),
                "x.png",
                "Kunde",
                "digital",
                True,
            )
