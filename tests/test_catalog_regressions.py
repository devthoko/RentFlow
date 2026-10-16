from sqlalchemy import select, func
from sqlalchemy.orm import Session
from rentflow.models import *
from rentflow.db import transaction
from rentflow import domain as d, fulfilment as f
from test_workflow import invoiced, pay, protocol
from test_documents import offered, contracted, signature
from conftest import token


def test_package_edit_preserves_existing_order_snapshot(offered, app, admin):
    with transaction(app.state.engine) as db:
        actor = db.scalar(select(User))
        order = db.get(Order, offered)
        item = db.scalar(select(Item))
        package = d.package_save(
            db,
            actor,
            {
                "name": "Tischset",
                "price": "20",
                "tax": "19",
                "components": {item.id: "2"},
            },
        )
        d.add_line(
            db,
            actor,
            order,
            {"kind": "package", "package_id": package.id, "quantity": "3"},
        )
        pid = package.id
        itemid = item.id
    assert admin.get("/items?package_edit=" + str(pid)).status_code == 200
    r = admin.post(
        "/packages",
        data={
            "csrf": token(admin, "/items"),
            "id": pid,
            "name": "Tischset neu",
            "price": "30",
            "tax": "7",
            "part_" + str(itemid): "4",
        },
    )
    assert r.status_code == 200
    with Session(app.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(Package)) == 1
        order = db.get(Order, offered)
        line = order.lines[-1]
        assert line["unit_cents"] == 2000 and line["tax"] == "19"
        assert d.physical([line])[0]["quantity"] == "6"


def test_multiple_images_survive_catalog_edit(offered, admin, app):
    with Session(app.state.engine) as db:
        itemid = db.scalar(select(Item.id))
    for name in ["erstes.png", "zweites.png"]:
        r = admin.post(
            f"/items/{itemid}/image",
            data={"csrf": token(admin, "/items")},
            files={"file": (name, signature(), "image/png")},
        )
        assert r.status_code == 200
    with Session(app.state.engine) as db:
        item = db.get(Item, itemid)
        assert len(item.image_ids) == 2 and item.image_id == item.image_ids[-1]


def test_small_business_totals_match_pdf_and_ui(offered, app, admin):
    with transaction(app.state.engine) as db:
        order = db.get(Order, offered)
        old = d.effective_lines(db, order)
        company = d.setting(db, "company")
        company["tax_mode"] = "small"
        d.set_setting(db, "company", company)
        assert d.effective_lines(db, order) == old
        d.touch(order)
        assert d.totals(d.effective_lines(db, order))["gross_cents"] == 10000
    response = admin.get(f"/orders/{offered}?step=3")
    assert "100,00 €" in response.text and "119,00 €" not in response.text


def test_identical_handover_save_does_not_create_new_document(invoiced, app):
    with transaction(app.state.engine) as db:
        actor = db.scalar(select(User))
        order = db.get(Order, invoiced)
        pay(db, app, actor, order, "119")
        data = protocol(order)
        f.handover_save(db, app.state.config, actor, order, data)
        original = order.handover_id
        f.handover_save(db, app.state.config, actor, order, data)
        assert order.handover_id == original
        assert (
            db.scalar(
                select(func.count())
                .select_from(Document)
                .where(Document.kind == "handover")
            )
            == 1
        )
