import copy, hashlib, json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo
from sqlalchemy import select, func
from .models import *
from .security import email


class RuleError(ValueError):
    pass


def required(value, label):
    value = str(value or "").strip()
    if not value:
        raise RuleError(f"{label} ist erforderlich.")
    if len(value) > 20000:
        raise RuleError(f"{label} ist zu lang.")
    return value


def decimal(value):
    try:
        s = str(value).strip()
        if "," in s:
            s = s.replace(".", "").replace(",", ".")
        result = Decimal(s)
        if not result.is_finite():
            raise InvalidOperation()
        return result
    except (InvalidOperation, ValueError):
        raise RuleError("Bitte eine gültige Zahl eingeben.")


def money(value):
    d = decimal(value)
    if d < 0 or d > 100000000:
        raise RuleError("Der Betrag muss zwischen 0 und 100.000.000 Euro liegen.")
    if d != d.quantize(Decimal(".01")):
        raise RuleError("Geldbeträge dürfen höchstens zwei Nachkommastellen haben.")
    return int(d * 100)


def quantity(value):
    d = decimal(value)
    if d <= 0 or d > 100000 or d != d.quantize(Decimal(".001")):
        raise RuleError(
            "Mengen müssen positiv sein und dürfen höchstens drei Nachkommastellen haben."
        )
    return str(d)


def tax_rate(value):
    d = decimal(value)
    if d < 0 or d > 100 or d != d.quantize(Decimal(".01")):
        raise RuleError("Ungültiger Umsatzsteuersatz.")
    return str(d)


def today():
    return datetime.now(ZoneInfo("Europe/Berlin")).date()


def booking_date(value):
    try:
        result = date.fromisoformat(str(value))
    except ValueError:
        raise RuleError("Bitte ein gültiges Zahlungsdatum angeben.")
    if result > today():
        raise RuleError(
            "Ein tatsächlicher Zahlungseingang darf nicht in der Zukunft liegen."
        )
    return result.isoformat()


def setting(db, key, default=None):
    row = db.get(Setting, key)
    return copy.deepcopy(row.value) if row else (default if default is not None else {})


def set_setting(db, key, value):
    row = db.get(Setting, key)
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))


def audit(db, actor, action, detail=None, order=None):
    last = db.scalar(select(Audit).order_by(Audit.id.desc()).limit(1))
    previous = last.digest if last else "0" * 64
    stamp = now()
    actor_id = actor.id if actor else None
    payload = {
        "actor": actor_id,
        "order": order.id if order else None,
        "action": action,
        "detail": detail or {},
        "time": stamp,
    }
    digest = hashlib.sha256(
        (previous + json.dumps(payload, sort_keys=True, ensure_ascii=False)).encode()
    ).hexdigest()
    db.add(
        Audit(
            actor_id=actor_id,
            order_id=payload["order"],
            action=action,
            detail=payload["detail"],
            created_at=stamp,
            previous=previous,
            digest=digest,
        )
    )
    db.flush()


def number(db, prefix):
    key = f"{prefix}-{today().year}"
    counter = db.get(Counter, key)
    if not counter:
        counter = Counter(key=key, value=0)
        db.add(counter)
    counter.value += 1
    db.flush()
    return f"{key}-{counter.value:05d}"


def customer_save(db, actor, data, customer_id=None):
    customer = db.get(Customer, customer_id) if customer_id else Customer()
    if not customer:
        raise RuleError("Kunde nicht gefunden.")
    customer.name = required(data.get("name"), "Vor- und Nachname")
    customer.email = email(data.get("email", ""))
    for field in ["phone", "address", "contact", "notes"]:
        setattr(customer, field, str(data.get(field, "")).strip())
    customer.address_data = {
        k: str(data.get(k, "")).strip()
        for k in ["street", "postcode", "city", "country"]
    }
    if all(customer.address_data.get(k) for k in ["street", "postcode", "city"]):
        customer.address = (
            customer.address_data["street"]
            + "\n"
            + customer.address_data["postcode"]
            + " "
            + customer.address_data["city"]
            + "\n"
            + (customer.address_data.get("country") or "DE")
        )
    customer.business = False
    customer.routing_id = ""
    db.add(customer)
    db.flush()
    audit(db, actor, "customer.saved", {"id": customer.id})
    return customer


def item_save(db, actor, data, item_id=None):
    item = db.get(Item, item_id) if item_id else Item()
    if not item:
        raise RuleError("Artikel nicht gefunden.")
    item.sku = required(data.get("sku"), "Artikelnummer")
    item.name = required(data.get("name"), "Name")
    item.cents = money(data.get("price", "0"))
    item.tax = tax_rate(data.get("tax", "19"))
    item.replacement_cents = money(data.get("replacement", "0"))
    item.category = str(data.get("category", ""))
    item.description = str(data.get("description", ""))
    db.add(item)
    db.flush()
    audit(db, actor, "item.saved", {"id": item.id})
    return item


def package_save(db, actor, data):
    parts = []
    for item_id, count in data.get("components", {}).items():
        if decimal(count or "0") == 0:
            continue
        item = db.get(Item, int(item_id))
        if not item:
            raise RuleError("Paketartikel nicht gefunden.")
        parts.append({"item_id": item.id, "quantity": quantity(count)})
    if not parts:
        raise RuleError("Ein Paket benötigt mindestens einen Artikel.")
    obj = db.get(Package, int(data["id"])) if data.get("id") else Package()
    if not obj:
        raise RuleError("Paket nicht gefunden.")
    obj.name = required(data.get("name"), "Paketname")
    obj.description = data.get("description", "")
    obj.cents = money(data.get("price", "0"))
    obj.tax = tax_rate(data.get("tax", "19"))
    obj.components = parts
    db.add(obj)
    db.flush()
    audit(db, actor, "package.saved", {"id": obj.id})
    return obj


def new_order(db, actor, customer_id):
    if not db.get(Customer, customer_id):
        raise RuleError("Bitte einen vorhandenen Kunden auswählen.")
    obj = Order(
        number=number(db, "AU"),
        customer_id=customer_id,
        event={},
        lines=[],
        handover={},
        returned={},
    )
    db.add(obj)
    db.flush()
    audit(db, actor, "order.created", order=obj)
    return obj


def editable(order):
    if order.closed_at:
        raise RuleError("Der Auftrag ist abgeschlossen.")
    if order.invoice_id or order.handed_at:
        raise RuleError(
            "Nach Rechnungsausstellung ist eine ausdrückliche Rechnungskorrektur erforderlich."
        )


def touch(order):
    editable(order)
    order.revision += 1
    order.offer_id = order.contract_id = order.packing_id = order.handover_id = None
    order.handover = {}


def validate_event(data):
    event = {
        k: str(data.get(k, "")).strip()
        for k in [
            "name",
            "date",
            "mode",
            "handover_at",
            "return_at",
            "address",
            "venue",
            "notes",
            "contact",
        ]
    }
    required(event["name"], "Eventname")
    if event["mode"] not in ["pickup", "delivery"]:
        raise RuleError("Bitte Abholung oder Lieferung auswählen.")
    if event["mode"] == "delivery":
        required(event["address"], "Lieferadresse")
    try:
        eventdate = date.fromisoformat(event["date"])
        start = datetime.fromisoformat(event["handover_at"])
        end = datetime.fromisoformat(event["return_at"])
    except ValueError:
        raise RuleError(
            "Eventdatum, Übergabetermin und Rückgabetermin müssen gültig sein."
        )
    if start.tzinfo or end.tzinfo:
        raise RuleError(
            "Bitte Termine in Ortszeit Europe/Berlin ohne Zeitzonenanhang angeben."
        )
    if start >= end or start.date() > eventdate or end.date() < eventdate:
        raise RuleError(
            "Übergabe muss vor der Rückgabe liegen und das Event zwischen beiden Terminen."
        )
    return event


def event_save(db, actor, order, data):
    event = validate_event(data)
    deposit = money(data.get("deposit", "0"))
    touch(order)
    order.event = event
    order.deposit_cents = deposit
    audit(db, actor, "order.event_saved", order=order)


def item_snapshot(item, count="1"):
    return {
        "item_id": item.id,
        "sku": item.sku,
        "name": item.name,
        "quantity": quantity(count),
        "replacement_cents": item.replacement_cents,
    }


def add_line(db, actor, order, data):
    editable(order)
    count = quantity(data.get("quantity", "1"))
    kind = data.get("kind", "free")
    parts = []
    if kind == "item":
        item = db.get(Item, int(data.get("item_id", 0)))
        if not item:
            raise RuleError("Artikel nicht gefunden.")
        name, description, cents, tax = (
            item.name,
            item.description,
            item.cents,
            item.tax,
        )
        parts = [item_snapshot(item)]
    elif kind == "package":
        package = db.get(Package, int(data.get("package_id", 0)))
        if not package:
            raise RuleError("Paket nicht gefunden.")
        name, description, cents, tax = (
            package.name,
            package.description,
            package.cents,
            package.tax,
        )
        parts = [
            item_snapshot(db.get(Item, part["item_id"]), part["quantity"])
            for part in package.components
        ]
    elif kind == "free":
        name = required(data.get("name"), "Positionsbezeichnung")
        description = data.get("description", "")
        cents = money(data.get("price", "0"))
        tax = tax_rate(data.get("tax", "19"))
    else:
        raise RuleError("Unbekannte Positionsart.")
    touch(order)
    order.lines = order.lines + [
        {
            "id": uid(),
            "name": name,
            "description": description,
            "quantity": count,
            "unit_cents": cents,
            "tax": tax,
            "parts": parts,
        }
    ]
    audit(db, actor, "order.line_added", order=order)


def totals(lines):
    net = 0
    groups = {}
    for line in lines:
        value = int(
            (decimal(line["quantity"]) * line["unit_cents"]).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
        net += value
        groups[line["tax"]] = groups.get(line["tax"], 0) + value
    taxes = [
        {
            "rate": rate,
            "net_cents": amount,
            "tax_cents": int(
                (Decimal(amount) * decimal(rate) / 100).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
            ),
        }
        for rate, amount in groups.items()
    ]
    tax = sum(row["tax_cents"] for row in taxes)
    return {
        "net_cents": net,
        "tax_cents": tax,
        "gross_cents": net + tax,
        "taxes": taxes,
    }


def physical(lines):
    return [
        {
            **part,
            "key": line["id"] + ":" + str(part["item_id"]),
            "quantity": str(decimal(line["quantity"]) * decimal(part["quantity"])),
        }
        for line in lines
        for part in line.get("parts", [])
    ]


def signed(db, document_id):
    return bool(
        document_id
        and db.scalar(select(Evidence.id).where(Evidence.document_id == document_id))
    )


def paid(db, invoice_id):
    return (
        db.scalar(
            select(func.coalesce(func.sum(Payment.cents), 0)).where(
                Payment.invoice_id == invoice_id
            )
        )
        if invoice_id
        else 0
    )


def outstanding(db, order):
    invoice = db.get(Document, order.invoice_id) if order.invoice_id else None
    return (
        max(0, invoice.snapshot["totals"]["gross_cents"] - paid(db, invoice.id))
        if invoice
        else None
    )


def deposit_balance(db, order):
    rows = db.scalars(select(Deposit).where(Deposit.order_id == order.id)).all()
    received = sum(r.cents for r in rows if r.kind == "received")
    refunded = sum(r.cents for r in rows if r.kind == "refunded")
    retained = sum(r.cents for r in rows if r.kind == "retained")
    return {
        "received": received,
        "refunded": refunded,
        "retained": retained,
        "remaining": received - refunded - retained,
    }


def handover_gate(db, order):
    if order.closed_at:
        raise RuleError("Der Auftrag ist abgeschlossen.")
    if not signed(db, order.offer_id):
        raise RuleError("Das aktuelle Angebot muss unterschrieben sein.")
    contract = db.get(Document, order.contract_id) if order.contract_id else None
    if (
        not contract
        or not signed(db, contract.id)
        or contract.snapshot.get("offer_id") != order.offer_id
    ):
        raise RuleError(
            "Der aktuelle, zum Angebot gehörende Mietvertrag muss unterschrieben sein."
        )
    invoice = db.get(Document, order.invoice_id) if order.invoice_id else None
    if not invoice or invoice.snapshot.get("contract_id") != order.contract_id:
        raise RuleError("Eine gültige Rechnung zum aktuellen Vertrag ist erforderlich.")
    due = outstanding(db, order)
    if due:
        raise RuleError(
            f"Übergabe nicht möglich. Es sind noch {due / 100:.2f} Euro offen."
        )


def workflow(db, order):
    due = outstanding(db, order)
    if order.closed_at:
        step, label, action = 9, "Auftrag abgeschlossen", "Archiv ansehen"
    elif not order.event:
        step, label, action = 2, "Eventinfos fehlen", "Eventinfos erfassen"
    elif not order.offer_id:
        step, label, action = 3, "Angebot in Bearbeitung", "Angebot fertigstellen"
    elif not signed(db, order.offer_id):
        step, label, action = (
            3,
            "Wartet auf unterschriebenes Angebot",
            "Unterschrift erfassen",
        )
    elif not order.contract_id:
        step, label, action = 4, "Mietvertrag erstellen", "Mietvertrag erstellen"
    elif not signed(db, order.contract_id):
        step, label, action = (
            4,
            "Wartet auf unterschriebenen Mietvertrag",
            "Unterschrift erfassen",
        )
    elif not order.invoice_id:
        step, label, action = 5, "Rechnung erstellen", "Rechnung erstellen"
    elif due:
        step, label, action = (
            5,
            "Übergabe wegen offener Zahlung gesperrt",
            "Zahlung erfassen",
        )
    elif not order.handed_at:
        step, label, action = 7, "Übergabe vorbereiten", "Übergabe dokumentieren"
    elif not order.returned_at:
        step, label, action = 8, "Wartet auf Rücknahme", "Rücknahme erfassen"
    elif deposit_balance(db, order)["remaining"]:
        step, label, action = 9, "Kaution noch abzurechnen", "Kaution abrechnen"
    else:
        step, label, action = 9, "Bereit zum Abschluss", "Auftrag beenden"
    return {"step": step, "label": label, "action": action, "outstanding": due}


def effective_lines(db, order):
    import copy

    document_id = order.invoice_id or order.contract_id or order.offer_id
    if document_id:
        return copy.deepcopy(db.get(Document, document_id).snapshot["lines"])
    lines = copy.deepcopy(order.lines)
    if setting(db, "company").get("tax_mode") == "small":
        for line in lines:
            line["tax"] = "0"
    return lines
