import copy
from datetime import timedelta
from sqlalchemy import select
from .models import *
from . import domain as d
from . import documents as docs


def snapshot(db, order):
    customer = db.get(Customer, order.customer_id)
    company = d.setting(db, "company")
    lines = copy.deepcopy(order.lines)
    if company.get("tax_mode") == "small":
        for line in lines:
            line["tax"] = "0"
    return {
        "order_number": order.number,
        "customer": {
            k: getattr(customer, k)
            for k in ["name", "email", "address", "phone", "address_data"]
        },
        "company": company,
        "event": copy.deepcopy(order.event),
        "lines": lines,
        "totals": d.totals(lines),
        "physical": d.physical(lines),
        "deposit_cents": order.deposit_cents,
        "revision": order.revision,
    }


def offer(db, config, actor, order, data):
    d.editable(order)
    if order.offer_id:
        return
    d.validate_event(order.event)
    if not order.lines:
        raise d.RuleError("Das Angebot benötigt mindestens eine Position.")
    order.offer_id = docs.create(
        db, config, actor, order, "offer", snapshot(db, order), d.number(db, "AN")
    ).id


def contract(db, config, actor, order, data):
    if not d.signed(db, order.offer_id):
        raise d.RuleError(
            "Ohne unterschriebenes aktuelles Angebot darf kein Mietvertrag erstellt werden."
        )
    if order.contract_id:
        return
    template = d.setting(db, "contract")
    text = d.required(template.get("text"), "Mietvertragstext in den Einstellungen")
    snap = copy.deepcopy(db.get(Document, order.offer_id).snapshot)
    snap.update(
        offer_id=order.offer_id,
        contract_text=text,
        template_version=template.get("version", 1),
    )
    order.contract_id = docs.create(
        db, config, actor, order, "contract", snap, d.number(db, "MV")
    ).id


def invoice(db, config, actor, order, data):
    if not d.signed(db, order.offer_id) or not d.signed(db, order.contract_id):
        raise d.RuleError("Angebot und Mietvertrag müssen unterschrieben sein.")
    if order.invoice_id:
        return
    contract = db.get(Document, order.contract_id)
    if contract.snapshot.get("offer_id") != order.offer_id:
        raise d.RuleError("Der Mietvertrag gehört nicht zum aktuellen Angebot.")
    snap = copy.deepcopy(contract.snapshot)
    snap.pop("contract_text", None)
    if not snap["customer"].get("address"):
        snap["customer"]["address"] = db.get(Customer, order.customer_id).address
    customer = db.get(Customer, order.customer_id)
    snap["customer"].update(
        address=customer.address, address_data=customer.address_data
    )
    current_company = d.setting(db, "company")
    if current_company.get("tax_mode") != snap["company"].get("tax_mode"):
        raise d.RuleError(
            "Die Besteuerungsart wurde geändert. Bitte ein neues Angebot erstellen und unterschreiben lassen."
        )
    snap["company"] = current_company
    d.required(snap["customer"].get("address"), "Rechnungsanschrift des Kunden")
    d.required(snap["company"].get("tax_id"), "Steuernummer / USt-IdNr. der Firma")
    snap.update(
        contract_id=order.contract_id,
        due_date=(d.today() + timedelta(days=14)).isoformat(),
    )
    invoice = docs.create(db, config, actor, order, "invoice", snap, d.number(db, "RE"))
    order.invoice_id = invoice.id


def payment(db, config, actor, order, data):
    if not order.invoice_id:
        raise d.RuleError("Zuerst eine Rechnung erstellen.")
    cents = d.money(data.get("amount", "0"))
    if cents <= 0:
        raise d.RuleError("Der Zahlungseingang muss größer als 0 sein.")
    if cents > d.outstanding(db, order):
        raise d.RuleError("Der Betrag überschreitet den offenen Rechnungsbetrag.")
    method = data.get("method")
    if method not in ["bank", "cash", "card", "other"]:
        raise d.RuleError("Bitte eine gültige Zahlungsart auswählen.")
    if str(data.get("actual", "")) not in ["on", "true", "1"]:
        raise d.RuleError("Bitte den tatsächlichen Zahlungseingang bestätigen.")
    row = Payment(
        invoice_id=order.invoice_id,
        cents=cents,
        date=d.booking_date(data.get("date")),
        method=method,
        reference=data.get("reference", ""),
        actor_id=actor.id,
    )
    db.add(row)
    db.flush()
    d.audit(
        db, actor, "payment.received", {"payment_id": row.id, "cents": cents}, order
    )


def reverse_payment(db, config, actor, order, data):
    row = db.get(Payment, data.get("payment_id"))
    if not row or row.invoice_id != order.invoice_id or row.cents <= 0:
        raise d.RuleError("Zahlung nicht gefunden.")
    if db.scalar(select(Payment.id).where(Payment.reversal_of == row.id)):
        raise d.RuleError("Diese Zahlung wurde bereits gegengebucht.")
    reason = d.required(data.get("reason"), "Begründung der Gegenbuchung")
    if data.get("method") not in ["correction", "refund"]:
        raise d.RuleError("Bitte Korrektur oder tatsächliche Erstattung auswählen.")
    if data.get("method") == "refund" and str(data.get("actual", "")) not in [
        "on",
        "true",
        "1",
    ]:
        raise d.RuleError("Bitte die tatsächliche Rückzahlung bestätigen.")
    reverse = Payment(
        invoice_id=row.invoice_id,
        cents=-row.cents,
        date=d.booking_date(data.get("date")),
        method=data["method"],
        reference=reason,
        reversal_of=row.id,
        actor_id=actor.id,
    )
    db.add(reverse)
    db.flush()
    d.audit(
        db,
        actor,
        "payment.reversed",
        {"payment_id": reverse.id, "original": row.id, "reason": reason},
        order,
    )


def cancel_invoice(db, config, actor, order, data):
    if order.handed_at:
        raise d.RuleError(
            "Nach abgeschlossener Übergabe ist ein Storno dieses Mietvorgangs nicht möglich."
        )
    if not order.invoice_id:
        raise d.RuleError("Keine aktuelle Rechnung vorhanden.")
    if d.paid(db, order.invoice_id) != 0:
        raise d.RuleError(
            "Bereits erfasste Zahlungen müssen vor dem Storno nachvollziehbar ausgeglichen werden."
        )
    obj = db.get(Document, order.invoice_id)
    snap = copy.deepcopy(obj.snapshot)
    snap.update(
        cancelled_id=obj.id,
        cancelled_number=obj.number,
        reason=d.required(data.get("reason"), "Stornobegründung"),
    )
    credit = docs.create(db, config, actor, order, "credit", snap, d.number(db, "ST"))
    order.invoice_id = order.packing_id = order.handover_id = None
    order.handover = {}
    d.audit(
        db,
        actor,
        "invoice.cancelled",
        {"invoice_id": obj.id, "reason": snap["reason"]},
        order,
    )


def packing(db, config, actor, order, data):
    if not order.invoice_id:
        raise d.RuleError("Zuerst eine Rechnung erstellen.")
    if not order.packing_id:
        order.packing_id = docs.create(
            db,
            config,
            actor,
            order,
            "packing",
            db.get(Document, order.invoice_id).snapshot,
        ).id


def execute(db, config, actor, order, action, data):
    actions = {
        "offer": offer,
        "contract": contract,
        "invoice": invoice,
        "payment": payment,
        "reverse-payment": reverse_payment,
        "cancel-invoice": cancel_invoice,
        "packing": packing,
    }
    from .fulfilment import ACTIONS

    actions.update(ACTIONS)
    if order.closed_at:
        raise d.RuleError("Der Auftrag ist abgeschlossen.")
    if action not in actions:
        raise d.RuleError("Unbekannte Aktion.")
    return actions[action](db, config, actor, order, data)
