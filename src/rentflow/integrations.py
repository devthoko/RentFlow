import hashlib, smtplib, ssl
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
from email.utils import formataddr
from urllib.parse import quote
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import *
from .db import transaction
from .security import decrypt
from . import domain as d, documents as docs


class DeliveryUncertain(Exception):
    pass


def send_smtp(config, settings, job, document=None, attachment=None):
    if not settings.get("host"):
        raise ValueError("SMTP ist noch nicht konfiguriert.")
    message = EmailMessage()
    message["From"] = formataddr((settings["sender_name"], settings["sender"]))
    message["To"] = job.payload["recipient"]
    message["Subject"] = (
        "RentFlow Test-E-Mail"
        if not document
        else docs.TITLES.get(document.kind, document.kind)
        + " "
        + (document.number or "")
    )
    message["Message-ID"] = "<" + job.id + "@rentflow.local>"
    message.set_content(
        "Dies ist eine Test-E-Mail von RentFlow."
        if not document
        else "Guten Tag,\n\nanbei erhalten Sie Ihr Dokument "
        + (document.number or "")
        + ".\n\nFreundliche Grüße\n"
        + settings["sender_name"]
    )
    if document:
        message.add_attachment(
            attachment,
            maintype="application",
            subtype="pdf",
            filename=(document.number or document.kind) + ".pdf",
        )
    context = ssl.create_default_context()
    server = None
    accepted = False
    try:
        if settings.get("mode") == "ssl":
            server = smtplib.SMTP_SSL(
                settings["host"], settings["port"], timeout=25, context=context
            )
        else:
            server = smtplib.SMTP(settings["host"], settings["port"], timeout=25)
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
        if settings.get("username"):
            server.login(
                settings["username"], decrypt(config, settings.get("password", ""))
            )
        try:
            refused = server.send_message(message)
            if refused:
                raise smtplib.SMTPRecipientsRefused(refused)
            accepted = True
        except (smtplib.SMTPServerDisconnected, TimeoutError, OSError) as exc:
            raise DeliveryUncertain(
                "Verbindung während der Übermittlung unterbrochen; Annahme unklar. Vor erneutem Versand prüfen."
            ) from exc
    finally:
        if server:
            try:
                server.quit()
            except Exception:
                try:
                    server.close()
                except Exception:
                    pass
    return accepted


def upload_webdav(config, settings, obj, content):
    if not settings.get("url"):
        raise ValueError("WebDAV ist noch nicht konfiguriert.")
    base = settings["url"].rstrip("/") + "/RentFlow"
    target = base + "/" + quote(obj.filename, safe="")
    with httpx.Client(
        auth=(settings["username"], decrypt(config, settings.get("password", ""))),
        timeout=30,
        follow_redirects=False,
        verify=True,
    ) as client:
        response = client.request("MKCOL", base)
        if response.status_code not in [201, 405]:
            raise ValueError(
                f"WebDAV-Verzeichnis konnte nicht erstellt werden (HTTP {response.status_code})."
            )
        response = client.put(
            target,
            content=content,
            headers={"If-None-Match": "*", "Content-Type": "application/octet-stream"},
        )
        if response.status_code == 412:
            check = client.get(target)
            if (
                check.status_code == 200
                and hashlib.sha256(check.content).hexdigest() == obj.sha256
            ):
                return
            raise ValueError(
                "WebDAV-Zieldatei existiert mit abweichender Prüfsumme. Keine Überschreibung."
            )
        if response.status_code not in [200, 201, 204]:
            raise ValueError(
                f"WebDAV-Upload fehlgeschlagen (HTTP {response.status_code})."
            )
        check = client.get(target)
        if (
            check.status_code != 200
            or hashlib.sha256(check.content).hexdigest() != obj.sha256
        ):
            raise ValueError(
                "WebDAV-Prüfsumme konnte nach dem Upload nicht bestätigt werden."
            )


def process_one(engine, config):
    nowtime = datetime.now(timezone.utc)
    with transaction(engine) as db:
        stale = db.scalars(
            select(Job).where(
                Job.status == "running", Job.next_at < nowtime.isoformat()
            )
        ).all()
        for old in stale:
            old.status = "uncertain" if old.kind == "smtp" else "failed"
            old.error = "Verarbeitung wurde unterbrochen. Status erneut prüfen."
        job = db.scalar(
            select(Job)
            .where(
                Job.status.in_(["pending", "failed"]),
                Job.next_at <= nowtime.isoformat(),
                Job.attempts < 5,
            )
            .order_by(Job.created_at)
            .limit(1)
        )
        if not job:
            return False
        settings = d.setting(db, job.kind)
        if not settings:
            job.status = "disabled"
            job.error = (
                "SMTP" if job.kind == "smtp" else "WebDAV"
            ) + " ist noch nicht konfiguriert."
            return True
        job.status = "running"
        job.attempts += 1
        job.next_at = (nowtime + timedelta(minutes=5)).isoformat()
        job_id = job.id
        obj = (
            db.get(Document, job.document_id)
            if job.document_id
            else db.get(Asset, job.asset_id)
            if job.asset_id
            else None
        )
    try:
        content = docs.read(config, obj) if obj else None
        if job.kind == "smtp":
            send_smtp(config, settings, job, obj, content)
        elif job.kind == "webdav":
            upload_webdav(config, settings, obj, content)
        else:
            raise ValueError("Unbekannte Verbindungsart.")
        status, error = "success", ""
        finished = now()
    except DeliveryUncertain as exc:
        status, error, finished = "uncertain", str(exc), None
    except Exception as exc:
        status, finished = "failed", None
        error = (
            str(exc)
            if isinstance(exc, ValueError)
            else type(exc).__name__ + ": Verbindung oder Anmeldung fehlgeschlagen."
        )
    with transaction(engine) as db:
        current = db.get(Job, job_id)
        current.status = status
        current.error = error
        current.finished_at = finished
        current.next_at = (
            datetime.now(timezone.utc)
            + timedelta(seconds=min(3600, 30 * 2**current.attempts))
        ).isoformat()
        d.audit(
            db,
            None,
            "integration." + status,
            {"job_id": job_id, "kind": job.kind, "error": error},
        )
    return True


def run_batch(engine, config, limit=20):
    for _ in range(limit):
        if not process_one(engine, config):
            break


if __name__ == "__main__":
    from .config import Config
    from .db import make_engine

    config = Config.environment()
    run_batch(make_engine(config.data), config)
