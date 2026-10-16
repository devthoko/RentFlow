from fastapi import Request, HTTPException
from sqlalchemy import select
from .main import require_user, csrf, redirect
from .db import transaction
from .models import *
from .security import email
from . import domain as d
from .web import idempotent


def register(app):
    @app.post("/documents/{document_id}/send")
    async def send_document(request: Request, document_id: str):
        data = dict(await request.form())
        csrf(request, data)
        with transaction(app.state.engine) as db:
            actor = require_user(request, db)
            document = db.get(Document, document_id)
            if not document or document.kind not in [
                "offer",
                "contract",
                "invoice",
                "credit",
            ]:
                raise d.RuleError(
                    "Dieses Dokument ist nicht für den Kundenversand vorgesehen."
                )
            if not d.setting(db, "smtp"):
                raise d.RuleError(
                    "SMTP muss zuerst in den Einstellungen eingerichtet werden."
                )
            recipient = email(data.get("recipient", ""))

            def enqueue():
                job = Job(
                    kind="smtp",
                    document_id=document.id,
                    payload={"recipient": recipient},
                )
                db.add(job)
                db.flush()
                d.audit(
                    db,
                    actor,
                    "mail.queued",
                    {
                        "job_id": job.id,
                        "document_id": document.id,
                        "recipient": recipient,
                    },
                    db.get(Order, document.order_id),
                )
                return {"job_id": job.id}

            idempotent(
                db, actor, data.get("op_key"), "mail." + document_id, data, enqueue
            )
        return redirect(
            request,
            "/documents/" + document_id,
            "E-Mail zum Versand vorgemerkt. Den tatsächlichen Status findest du im Versandverlauf.",
        )

    @app.post("/smtp-test")
    async def smtp_test(request: Request):
        data = dict(await request.form())
        csrf(request, data)
        with transaction(app.state.engine) as db:
            actor = require_user(request, db, True)
            if not d.setting(db, "smtp"):
                raise d.RuleError("Bitte zuerst SMTP konfigurieren.")

            def enqueue():
                job = Job(
                    kind="smtp", payload={"recipient": email(data.get("recipient", ""))}
                )
                db.add(job)
                db.flush()
                return {"job_id": job.id}

            idempotent(db, actor, data.get("op_key"), "smtp.test", data, enqueue)
            d.audit(db, actor, "mail.test_queued")
        return redirect(
            request,
            "/settings",
            "Testversand vorgemerkt. Ergebnis im Verbindungsverlauf.",
        )

    @app.post("/jobs/{job_id}/retry")
    async def retry(request: Request, job_id: str):
        data = dict(await request.form())
        csrf(request, data)
        with transaction(app.state.engine) as db:
            actor = require_user(request, db)
            job = db.get(Job, job_id)
            if not job:
                raise HTTPException(404, "Vorgang nicht gefunden.")
            if job.kind == "webdav" and actor.role != "admin":
                raise HTTPException(
                    403, "WebDAV-Wiederholungen dürfen nur Administratoren auslösen."
                )

            def enqueue():
                if job.status not in ["failed", "uncertain", "disabled"]:
                    raise d.RuleError(
                        "Dieser Vorgang kann nicht erneut gestartet werden."
                    )
                if job.status == "uncertain" and data.get("confirmed") != "on":
                    raise d.RuleError(
                        "Annahme unklar. Bitte den bisherigen Versand prüfen und den erneuten Versand ausdrücklich bestätigen."
                    )
                new = Job(
                    kind=job.kind,
                    document_id=job.document_id,
                    asset_id=job.asset_id,
                    payload={**job.payload, "retry_of": job.id},
                )
                job.status = "superseded"
                db.add(new)
                db.flush()
                d.audit(
                    db,
                    actor,
                    "integration.retry_queued",
                    {"original": job.id, "new": new.id},
                )
                return {"job_id": new.id}

            idempotent(db, actor, data.get("op_key"), "retry." + job_id, data, enqueue)
            target = "/documents/" + job.document_id if job.document_id else "/settings"
        return redirect(request, target, "Erneuter Versuch vorgemerkt.")

    @app.post("/webdav-retry")
    async def webdav_retry(request: Request):
        data = dict(await request.form())
        csrf(request, data)
        with transaction(app.state.engine) as db:
            actor = require_user(request, db, True)
            if not d.setting(db, "webdav"):
                raise d.RuleError("Bitte zuerst WebDAV konfigurieren.")
            jobs = db.scalars(
                select(Job).where(
                    Job.kind == "webdav", Job.status.in_(["disabled", "failed"])
                )
            ).all()
            for job in jobs:
                job.status = "pending"
                job.attempts = 0
                job.next_at = now()
            d.audit(db, actor, "webdav.retry_all", {"count": len(jobs)})
        return redirect(
            request, "/settings", "Ausstehende Dateien werden erneut synchronisiert."
        )
