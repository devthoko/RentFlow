import copy, io, os
from pathlib import Path
from pypdf import PdfReader
from sqlalchemy import select
from rentflow import documents as docs, domain as d
from rentflow.db import transaction
from rentflow.models import *
from test_documents import offered, contracted


def test_multipage_pdf_and_archived_signature(contracted, app):
    folder = Path("/tmp/rentflow-pdf-review")
    folder.mkdir(exist_ok=True)
    with transaction(app.state.engine) as db:
        actor = db.scalar(select(User))
        order = db.get(Order, contracted)
        for doc in db.scalars(select(Document)):
            (folder / (doc.kind + ".pdf")).write_bytes(docs.read(app.state.config, doc))
        snap = copy.deepcopy(db.get(Document, order.contract_id).snapshot)
        snap["lines"] = []
        for index in range(40):
            snap["lines"].append(
                {
                    "id": str(index),
                    "name": "Dekorationsartikel " + str(index + 1),
                    "description": "Mietartikel mit dokumentierter Ausführung. Tischdekoration für die vereinbarte Veranstaltung.",
                    "quantity": "3",
                    "unit_cents": 1250,
                    "tax": "19",
                }
            )
        snap["totals"] = d.totals(snap["lines"])
        snap["contract_text"] = (
            "Die Mietartikel werden zum vereinbarten Termin zurückgegeben. Schäden werden bei Übergabe und Rücknahme dokumentiert.\n\n"
            * 25
        )
        doc = docs.create(
            db, app.state.config, actor, order, "contract", snap, "MV-LAYOUT-TEST"
        )
        raw = docs.read(app.state.config, doc)
        reader = PdfReader(io.BytesIO(raw))
        assert len(reader.pages) >= 3
        text = "\n".join(p.extract_text() for p in reader.pages)
        assert (
            "Dekorationsartikel 40" in text
            and "1.785,00 EUR" in text
            and "MV-LAYOUT-TEST" in text
        )
        (folder / "mehrseitiger-vertrag.pdf").write_bytes(raw)
