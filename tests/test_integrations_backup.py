import hashlib
from pathlib import Path
from unittest.mock import patch
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from rentflow.models import *
from rentflow.db import transaction, make_engine
from rentflow import domain as d, integrations as i, maintenance as m
from test_documents import offered


def test_smtp_failure_recorded(offered, app):
    with transaction(app.state.engine) as db:
        for job in db.scalars(select(Job)):
            job.status = "disabled"
        d.set_setting(
            db,
            "smtp",
            {
                "host": "invalid",
                "port": 587,
                "mode": "starttls",
                "sender_name": "Test",
                "sender": "test@example.com",
            },
        )
        order = db.get(Order, offered)
        job = Job(
            kind="smtp",
            document_id=order.offer_id,
            payload={"recipient": "test@example.com"},
        )
        db.add(job)
        db.flush()
        jid = job.id
    with patch(
        "rentflow.integrations.send_smtp", side_effect=OSError("connection failed")
    ):
        assert i.process_one(app.state.engine, app.state.config)
    with Session(app.state.engine) as db:
        job = db.get(Job, jid)
        assert job.status == "failed" and not job.finished_at and job.attempts == 1


def test_uncertain_smtp_is_not_automatically_retried(offered, app):
    with transaction(app.state.engine) as db:
        for job in db.scalars(select(Job)):
            job.status = "disabled"
        d.set_setting(db, "smtp", {"host": "x"})
        job = Job(kind="smtp", payload={"recipient": "test@example.com"})
        db.add(job)
        db.flush()
        jid = job.id
    with patch(
        "rentflow.integrations.send_smtp", side_effect=i.DeliveryUncertain("uncertain")
    ):
        i.process_one(app.state.engine, app.state.config)
    with Session(app.state.engine) as db:
        assert db.get(Job, jid).status == "uncertain"
    assert i.process_one(app.state.engine, app.state.config) is False


def test_webdav_outage_preserves_original(offered, app):
    with transaction(app.state.engine) as db:
        d.set_setting(db, "webdav", {"url": "https://invalid", "username": "test"})
        order = db.get(Order, offered)
        doc = db.get(Document, order.offer_id)
        file = app.state.config.data / "objects" / doc.filename
        digest = doc.sha256
    with patch("rentflow.integrations.upload_webdav", side_effect=OSError("offline")):
        i.process_one(app.state.engine, app.state.config)
    assert file.exists() and hashlib.sha256(file.read_bytes()).hexdigest() == digest
    with Session(app.state.engine) as db:
        assert db.scalar(select(Job)).status == "failed"


def test_backup_and_restore(offered, app, tmp_path):
    archive = m.backup(app.state.engine, app.state.config)
    restored = tmp_path / "restore-test"
    cfg, version = m.restore(archive, restored)
    assert cfg["secret"] == app.state.config.secret
    engine = make_engine(restored)
    with Session(engine) as db:
        order = db.get(Order, offered)
        doc = db.get(Document, order.offer_id)
        assert (
            hashlib.sha256(
                (restored / "objects" / doc.filename).read_bytes()
            ).hexdigest()
            == doc.sha256
        )
    engine.dispose()
    with pytest.raises(ValueError):
        m.restore(archive, restored)


def test_employee_cannot_read_settings(admin, app):
    with transaction(app.state.engine) as db:
        db.scalar(select(User)).role = "employee"
    assert admin.get("/settings").status_code == 403
