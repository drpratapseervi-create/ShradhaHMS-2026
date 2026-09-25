"""
Pharmacy counter logic: turn an OPD prescription into bill lines (matched stock
item + suggested quantity), then create/cancel a PharmacyBill, deducting and
restoring batch stock in the same transaction.
"""

import math
import re
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from hms.models import InventoryItem, PharmacyBill, PharmacyBillItem
from .stock import issue_stock, reverse_issue, sellable_batches, sellable_quantity

# ── Quantity from frequency x duration ─────────────────────────────

_DOSE = r"(1/2|½|\d+(?:\.\d+)?)"  # "1/2" first, or "1/2" would match as "1"
_PATTERN_RE = re.compile(rf"{_DOSE}\s*-\s*{_DOSE}\s*-\s*{_DOSE}(?:\s*-\s*{_DOSE})?")
_DURATION_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(d|day|days|dyas|dys|w|wk|wks|week|weeks|m|mon|month|months)\b", re.I)


def _dose_value(s):
    return 0.5 if s in ("½", "1/2") else float(s)


def doses_per_day(frequency):
    """'(1-0-1) twice daily' -> 2.0; '(1-0-0) once a week' -> 1/7; unknown -> None."""
    f = (frequency or "").lower()
    if not f:
        return None
    m = _PATTERN_RE.search(f)
    if m:
        per_day = sum(_dose_value(g) for g in m.groups() if g)
    elif "thrice" in f or "tds" in f or "tid" in f:
        per_day = 3
    elif "twice" in f or " bd" in f or f.startswith("bd") or "bid" in f:
        per_day = 2
    elif "once" in f or " od" in f or f.startswith("od") or "hs" in f or "night" in f:
        per_day = 1
    else:
        return None  # SOS / stat / free text -> pharmacist decides
    if "week" in f:
        per_day /= 7
    return per_day


def duration_days(duration):
    m = _DURATION_RE.search(duration or "")
    if not m:
        return None
    n, unit = float(m.group(1)), m.group(2).lower()
    if unit.startswith("w"):
        return n * 7
    if unit.startswith("m"):
        return n * 30
    return n


def suggested_quantity(item, frequency, duration):
    """Units to dispense. Loose tablets/capsules: dose x days; bottles/tubes/vials: 1."""
    if item is None:
        return None
    if not item.sells_loose:
        return 1
    if (frequency or "").strip().lower() == "stat":
        return 1
    per_day, days = doses_per_day(frequency), duration_days(duration)
    if per_day is None or days is None:
        return None
    return max(1, math.ceil(per_day * days - 1e-9))


# ── Matching free-text prescription names to stock items ───────────

_PREFIX_RE = re.compile(r"^(tab|tabs|tablet|cap|caps|capsule|syp|syr|syrup|inj|injection|oint|ointment|drop|drops|gel|cream|susp)\b\.?\s*", re.I)


def normalize_name(name):
    n = re.sub(r"[^a-z0-9+ ]", " ", (name or "").lower())
    n = re.sub(r"\s+", " ", n).strip()
    return _PREFIX_RE.sub("", n).strip()


def build_item_index():
    """normalized name -> InventoryItem, from both the item name and its Drug Master name."""
    index = {}
    for item in InventoryItem.objects.select_related("drug").filter(category="Medicine"):
        for name in (item.name, item.drug.name if item.drug else None):
            key = normalize_name(name)
            if key:
                # Prefer an item that actually has stock when two share a name.
                if key not in index or (item.current_stock > 0 >= index[key].current_stock):
                    index[key] = item
    return index


def dispense_history(consultation_ids):
    """
    Per consultation, from its active (non-cancelled) bills:
      "dispensed": normalized names actually sold,
      "seen":      normalized names that were on the prescription when a bill was made
                   (sold or deliberately skipped),
      "billed":    whether any active bill exists.
    Matched by medicine name, not Prescription id: the consultation screen deletes and
    recreates its Prescription rows on every save, so ids don't survive.
    """
    hist = {cid: {"dispensed": set(), "seen": set(), "billed": False} for cid in consultation_ids}
    for cid, snapshot in (PharmacyBill.objects.filter(consultation_id__in=consultation_ids, status="PAID")
                          .values_list("consultation_id", "prescribed_snapshot")):
        hist[cid]["billed"] = True
        hist[cid]["seen"].update(normalize_name(n) for n in snapshot or [])
    for cid, name in (PharmacyBillItem.objects
                      .filter(bill__consultation_id__in=consultation_ids, bill__status="PAID")
                      .exclude(prescribed_as="").values_list("bill__consultation_id", "prescribed_as")):
        hist[cid]["dispensed"].add(normalize_name(name))
        hist[cid]["seen"].add(normalize_name(name))
    return hist


def prescription_lines(consultation):
    """Prefilled counter lines for every prescribed medicine on a consultation."""
    index = build_item_index()
    hist = dispense_history([consultation.id])[consultation.id]
    lines = []
    for rx in consultation.prescriptions.all():
        key = normalize_name(rx.medicine)
        item = index.get(key)
        lines.append({
            "prescription": rx,
            "item": item,
            "quantity": suggested_quantity(item, rx.frequency, rx.duration),
            **item_stock_info(item),
            "already_dispensed": key in hist["dispensed"],
            "skipped_before": key in hist["seen"] and key not in hist["dispensed"],
            "new_since_bill": hist["billed"] and key not in hist["seen"],
        })
    return lines


def _snapshot_for_new_bill(consultation):
    """
    The prescribed medicines this bill decides on (sells or skips): everything on the
    prescription except what's already been sold on another active bill. Keeping earlier
    bills' medicines out means cancelling that earlier bill reopens them.
    """
    if consultation is None:
        return []
    sold = dispense_history([consultation.id])[consultation.id]["dispensed"]
    return [m for m in consultation.prescriptions.values_list("medicine", flat=True)
            if normalize_name(m) not in sold]


def pending_consultations(date_from, date_to):
    """
    OPD consultations in the date range that still need the counter's attention:
    never dispensed, or a medicine was added to the prescription after it was dispensed.
    Returns (pending, done) lists of {"c": Consultation, "new": [medicine names]}.
    """
    from hms.models import Consultation

    consultations = list(
        Consultation.objects.filter(appointment__date__gte=date_from, appointment__date__lte=date_to,
                                    prescriptions__isnull=False)
        .select_related("appointment__patient", "appointment__doctor")
        .prefetch_related("prescriptions")
        .order_by("-appointment__date", "-appointment__time")
        .distinct()
    )
    hist = dispense_history([c.id for c in consultations])
    pending, done = [], []
    for c in consultations:
        h = hist[c.id]
        names = [rx.medicine for rx in c.prescriptions.all()]
        new = [n for n in names if h["billed"] and normalize_name(n) not in h["seen"]]
        row = {"c": c, "rx_count": len(names), "new": new}
        (pending if (not h["billed"] or new) else done).append(row)
    return pending, done


def item_stock_info(item):
    if item is None:
        return {"available": 0, "mrp": None}
    first = sellable_batches(item).first()
    return {"available": sellable_quantity(item), "mrp": first.mrp if first else None}


# ── Bills ──────────────────────────────────────────────────────────

def _financial_year(d):
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start % 100:02d}{(start + 1) % 100:02d}"


def _next_number(model, field, code):
    """PH/2627/00001 (bills), PR/2627/00001 (returns): consecutive per financial year, as GST requires."""
    prefix = f"{code}/{_financial_year(timezone.localdate())}/"
    last = (model.objects.select_for_update()
            .filter(**{f"{field}__startswith": prefix}).order_by(f"-{field}").first())
    seq = int(getattr(last, field).rsplit("/", 1)[1]) + 1 if last else 1
    return f"{prefix}{seq:05d}"


@transaction.atomic
def create_bill(*, lines, user, payment_mode="CASH", discount=0, patient=None, consultation=None,
                customer_name="", customer_mobile="", doctor=None, doctor_name="", admission=None):
    """
    lines: [{"item": InventoryItem, "quantity": int, "prescription": Prescription | None}]
    With `admission`, the bill is an inpatient issue charged to that admission's
    discharge bill (no discount, nothing collected at the counter).
    Deducts stock FEFO (a line may span batches). Raises InsufficientStock / ValueError
    and rolls everything back if any line can't be filled.
    """
    lines = [l for l in lines if l.get("item") and int(l.get("quantity") or 0) > 0]
    if not lines:
        raise ValueError("Add at least one medicine with a quantity.")
    if admission is not None:
        if admission.status != "ADMITTED":
            raise ValueError(f"{admission.ipd_no} is not currently admitted.")
        payment_mode, discount = "IPD", 0
        patient, doctor = admission.patient, admission.doctor
    elif payment_mode == "IPD":
        raise ValueError("Choose the admission to charge.")

    bill = PharmacyBill.objects.create(
        bill_no=_next_number(PharmacyBill, "bill_no", "PH"), patient=patient,
        consultation=consultation, admission=admission,
        customer_name=customer_name or (patient.full_name if patient else ""),
        customer_mobile=customer_mobile or (patient.mobile_no if patient else ""),
        doctor=doctor, doctor_name=doctor_name, payment_mode=payment_mode, created_by=user,
        prescribed_snapshot=_snapshot_for_new_bill(consultation),
    )
    detail = f"{bill.bill_no} {bill.display_name}"
    gross = Decimal("0")
    for line in lines:
        item = line["item"]
        for out in issue_stock(item=item, quantity=int(line["quantity"]), issued_to="Patient",
                               issued_to_detail=detail, user=user):
            amount = (out.batch.mrp * out.quantity).quantize(Decimal("0.01"))
            PharmacyBillItem.objects.create(
                bill=bill, item=item, batch=out.batch, stock_out=out,
                prescription=line.get("prescription"),
                prescribed_as=(line["prescription"].medicine[:200] if line.get("prescription") else ""),
                quantity=out.quantity,
                mrp=out.batch.mrp, gst_percent=item.gst_percent, amount=amount,
            )
            gross += amount

    discount = Decimal(str(discount or 0))
    if payment_mode == "FREE":
        discount = gross
    discount = max(Decimal("0"), min(discount, gross))
    bill.gross_amount, bill.discount, bill.net_amount = gross, discount, gross - discount
    bill.save(update_fields=["gross_amount", "discount", "net_amount"])
    return bill


@transaction.atomic
def cancel_bill(bill, *, user, reason):
    """Mark the bill cancelled (its number stays used) and put every unit back in its batch."""
    bill = PharmacyBill.objects.select_for_update().get(pk=bill.pk)
    if bill.status == "CANCELLED":
        return bill
    for bi in bill.items.select_related("stock_out"):
        if bi.stock_out:
            reverse_issue(bi.stock_out)
    bill.status = "CANCELLED"
    bill.cancelled_by, bill.cancelled_at, bill.cancel_reason = user, timezone.now(), reason[:200]
    bill.save(update_fields=["status", "cancelled_by", "cancelled_at", "cancel_reason"])
    return bill


# ── Partial returns ────────────────────────────────────────────────

@transaction.atomic
def return_items(bill, *, quantities, user, reason=""):
    """
    quantities: {PharmacyBillItem id: units being returned}. Each unit goes back
    into the batch it was sold from. The refund is valued at what was actually
    charged (MRP x the bill's discount share); for an IPD issue it reduces the
    admission's pharmacy charge instead of paying out cash.
    """
    from hms.models import PharmacyReturn, PharmacyReturnItem, InventoryItem, StockBatch

    bill = PharmacyBill.objects.select_for_update().get(pk=bill.pk)
    if bill.status == "CANCELLED":
        raise ValueError("This bill is cancelled; nothing can be returned.")
    wanted = {int(k): int(v) for k, v in quantities.items() if v and int(v) > 0}
    if not wanted:
        raise ValueError("Enter the quantity being returned.")

    items = {bi.id: bi for bi in bill.items.select_for_update().filter(id__in=wanted)}
    for bi_id, qty in wanted.items():
        bi = items.get(bi_id)
        if bi is None:
            raise ValueError("That medicine is not on this bill.")
        if qty > bi.returnable_quantity:
            raise ValueError(f"{bi.item.name}: only {bi.returnable_quantity} can be returned.")

    ret = PharmacyReturn.objects.create(
        return_no=_next_number(PharmacyReturn, "return_no", "PR"),
        bill=bill, reason=reason[:200], created_by=user,
    )
    factor, total = bill.discount_factor, Decimal("0")
    for bi_id, qty in wanted.items():
        bi = items[bi_id]
        amount = (bi.mrp * qty * factor).quantize(Decimal("0.01"))
        PharmacyReturnItem.objects.create(pharmacy_return=ret, bill_item=bi, quantity=qty, amount=amount)
        total += amount

        InventoryItem.objects.filter(pk=bi.item_id).update(current_stock=F("current_stock") + qty)
        StockBatch.objects.filter(pk=bi.batch_id).update(quantity_remaining=F("quantity_remaining") + qty)
        # Keep the StockOut equal to what's still out, so a later cancel restores only that.
        if bi.stock_out_id:
            bi.stock_out.quantity -= qty
            bi.stock_out.notes = (bi.stock_out.notes + f" [{qty} returned {ret.return_no}]").strip()
            bi.stock_out.save(update_fields=["quantity", "notes"])
        bi.returned_quantity += qty
        bi.save(update_fields=["returned_quantity"])

    ret.refund_amount = total
    ret.save(update_fields=["refund_amount"])
    bill.returned_amount += total
    bill.save(update_fields=["returned_amount"])
    return ret


# ── Inpatient (IPD) issue ──────────────────────────────────────────

IPD_PHARMACY_BILL_ITEM = "IPD Pharmacy (Medicines)"


def ipd_medication_lines(admission):
    """Counter lines prefilled from the admission's medication orders (quantity left to the pharmacist)."""
    from hms.models import IPDMedication

    index = build_item_index()
    lines = []
    for med in IPDMedication.objects.filter(admission=admission).select_related("drug"):
        item = None
        for name in (med.drug.name if med.drug else None, med.medicine_name):
            item = item or index.get(normalize_name(name))
        lines.append({
            "prescription": None,
            "order": med,
            "item": item,
            "quantity": None,
            **item_stock_info(item),
            "already_dispensed": False,
        })
    return lines


def ipd_pharmacy_total(admission):
    """What this admission owes for medicines: active IPD issues less returns."""
    total = Decimal("0")
    for b in PharmacyBill.objects.filter(admission=admission, status="PAID"):
        total += b.amount_after_returns
    return total


def sync_ipd_pharmacy_charge(discharge_bill, admission):
    """Keep one 'IPD Pharmacy (Medicines)' line on the discharge bill equal to ipd_pharmacy_total()."""
    from hms.models import BillItem, DischargeBillItem

    if discharge_bill.is_paid:
        return
    total = ipd_pharmacy_total(admission)
    bill_item, _ = BillItem.objects.get_or_create(
        name=IPD_PHARMACY_BILL_ITEM, defaults={"category": "Pharmacy", "price": 0},
    )
    line = DischargeBillItem.objects.filter(bill=discharge_bill, item=bill_item).first()
    if total > 0:
        if line is None:
            line = DischargeBillItem(bill=discharge_bill, item=bill_item)
        line.quantity, line.price, line.total = 1, total, total
        line.save()
    elif line is not None:
        line.delete()


# ── Cash collected at the counter ──────────────────────────────────

def counter_collection(date_from, date_to):
    """
    Cash/UPI actually taken at the pharmacy counter between two dates:
    sales on active non-IPD bills, less refunds given on them in the same period.
    IPD issues are collected on the discharge bill; cancelled bills count for neither.
    Returns (total, {payment_mode: amount}).
    """
    from hms.models import PharmacyReturn

    by_mode = {}
    for mode, amount in (PharmacyBill.objects
                         .filter(created_at__date__gte=date_from, created_at__date__lte=date_to, status="PAID")
                         .exclude(payment_mode="IPD").values_list("payment_mode", "net_amount")):
        by_mode[mode] = by_mode.get(mode, Decimal("0")) + amount
    for mode, amount in (PharmacyReturn.objects
                         .filter(created_at__date__gte=date_from, created_at__date__lte=date_to, bill__status="PAID")
                         .exclude(bill__payment_mode="IPD").values_list("bill__payment_mode", "refund_amount")):
        by_mode[mode] = by_mode.get(mode, Decimal("0")) - amount
    return sum(by_mode.values(), Decimal("0")), dict(sorted(by_mode.items()))
