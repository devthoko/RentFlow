import io, hashlib
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
import httpx, pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from pypdf import PdfWriter
from rentflow import documents as docs, domain as d, integrations as i
from rentflow.db import transaction
from rentflow.models import Job, Customer
from conftest import token
from test_documents import offered


def test_private_customers_only(admin, app):
    page = admin.get("/customers")
    assert "B2B" not in page.text and "Leitweg" not in page.text
    with transaction(app.state.engine) as db:
        from rentflow.models import User

        customer = d.customer_save(
            db,
            db.scalar(select(User)),
            {
                "name": "Privatkunde",
                "email": "privat@example.com",
                "business": "on",
                "routing_id": "123",
            },
        )
        assert not customer.business and not customer.routing_id


def test_active_pdf_is_rejected(offered, app):
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.add_js("app.alert('test')")
    buffer = io.BytesIO()
    writer.write(buffer)
    with transaction(app.state.engine) as db:
        with pytest.raises(d.RuleError):
            docs.asset(db, app.state.config, buffer.getvalue(), "unsafe.pdf", pdf=True)


def test_backup_admin_routes(admin, app):
    csrf = token(admin, "/settings")
    response = admin.post("/admin/backup", data={"csrf": csrf})
    assert response.status_code == 200 and "Herunterladen" in response.text
    archive = next((app.state.config.data / "backups").glob("*.tar.gz"))
    download = admin.get("/admin/backups/" + archive.name)
    assert download.status_code == 200 and download.content[:2] == b"\x1f\x8b"
    with transaction(app.state.engine) as db:
        from rentflow.models import User

        db.scalar(select(User)).role = "employee"
    assert admin.get("/admin/backups/" + archive.name).status_code == 403


def test_retry_is_idempotent_and_replaces_original(admin, app):
    with transaction(app.state.engine) as db:
        job = Job(
            kind="smtp", payload={"recipient": "test@example.com"}, status="failed"
        )
        db.add(job)
        db.flush()
        jid = job.id
    data = {
        "csrf": token(admin, "/settings"),
        "op_key": "retry-unique-operation-key-00001",
    }
    for _ in range(2):
        assert admin.post("/jobs/" + jid + "/retry", data=data).status_code == 200
    with Session(app.state.engine) as db:
        assert db.get(Job, jid).status == "superseded"
        assert db.scalar(select(func.count()).select_from(Job)) == 2


def test_smtp_tls_acceptance_and_attachment(app):
    server = MagicMock()
    server.send_message.return_value = {}
    settings = {
        "host": "mail.example.com",
        "port": 587,
        "mode": "starttls",
        "sender_name": "Verleih",
        "sender": "mail@example.com",
    }
    job = SimpleNamespace(id="test-id", payload={"recipient": "kunde@example.com"})
    doc = SimpleNamespace(kind="invoice", number="RE-TEST")
    with patch("rentflow.integrations.smtplib.SMTP", return_value=server):
        assert i.send_smtp(app.state.config, settings, job, doc, b"%PDF-test")
    server.starttls.assert_called_once()
    message = server.send_message.call_args.args[0]
    assert message["To"] == "kunde@example.com"
    assert next(message.iter_attachments()).get_payload(decode=True) == b"%PDF-test"


@pytest.mark.parametrize("existing", [False, True])
def test_webdav_no_overwrite_and_checksum(app, existing):
    raw = b"archive"
    digest = hashlib.sha256(raw).hexdigest()
    obj = SimpleNamespace(filename="unique.pdf", sha256=digest)
    calls = []

    def handle(req):
        calls.append(req.method)
        if req.method == "MKCOL":
            return httpx.Response(405)
        if req.method == "PUT":
            assert req.headers["if-none-match"] == "*"
            return httpx.Response(412 if existing else 201)
        return httpx.Response(200, content=raw)

    client = httpx.Client(transport=httpx.MockTransport(handle))
    with patch("rentflow.integrations.httpx.Client", return_value=client):
        i.upload_webdav(
            app.state.config,
            {"url": "https://dav.example.com", "username": "a"},
            obj,
            raw,
        )
    assert calls == ["MKCOL", "PUT", "GET"]


def test_webdav_conflicting_file_is_never_replaced(app):
    obj = SimpleNamespace(
        filename="unique.pdf", sha256=hashlib.sha256(b"good").hexdigest()
    )

    def handle(req):
        return httpx.Response(
            405 if req.method == "MKCOL" else 412 if req.method == "PUT" else 200,
            content=b"other",
        )

    with patch(
        "rentflow.integrations.httpx.Client",
        return_value=httpx.Client(transport=httpx.MockTransport(handle)),
    ):
        with pytest.raises(ValueError, match="Keine Überschreibung"):
            i.upload_webdav(
                app.state.config,
                {"url": "https://dav.example.com", "username": "a"},
                obj,
                b"good",
            )
