"""
Discharge bill for one admission: the per-day lines (bed by ward rate, nursing,
consultation) and the IPD pharmacy line are kept in sync from the admission; a
paid bill is never changed.
"""

from decimal import Decimal

from django.db import transaction

from hms.models import BillItem, DischargeBill, DischargeBillItem
from hms.pharmacy.dispensing import IPD_PHARMACY_BILL_ITEM, sync_ipd_pharmacy_charge
from .beds import bed_charge_nights, billable_days

# Per-day services charged for every day of the stay, matched by bill-item name (as before).
DAILY_SERVICES = ("Nursing", "Consultation")


def get_bill(admission):
    bill, _ = DischargeBill.objects.get_or_create(
        admission=admission,
        defaults={"patient": admission.patient, "total_amount": 0, "discount": 0,
                  "advance_paid": 0, "final_amount": 0},
    )
    return bill


def ward_charge_item_ids():
    from hms.models import Ward
    return set(Ward.objects.exclude(bed_charge_item__isnull=True).values_list("bed_charge_item_id", flat=True))


def desired_daily_lines(admission):
    """{BillItem: quantity} for the auto-maintained per-day lines."""
    lines = {}
    for ward, nights in bed_charge_nights(admission):
        if ward.bed_charge_item:
            lines[ward.bed_charge_item] = lines.get(ward.bed_charge_item, 0) + nights
    days = billable_days(admission)
    for name in DAILY_SERVICES:
        item = BillItem.objects.filter(name__icontains=name).exclude(name=IPD_PHARMACY_BILL_ITEM).first()
        if item:
            lines[item] = days
    return lines


@transaction.atomic
def sync_bill(bill, admission):
    if bill.is_paid:
        return
    desired = desired_daily_lines(admission)
    keep = set()
    for item, qty in desired.items():
        line = DischargeBillItem.objects.filter(bill=bill, item=item).first() or DischargeBillItem(bill=bill, item=item)
        line.quantity, line.price, line.total, line.auto_synced = qty, item.price, item.price * qty, True
        line.save()
        keep.add(line.pk)
    # Drop per-day lines this sync added earlier that no longer apply (e.g. after a transfer).
    (DischargeBillItem.objects.filter(bill=bill, auto_synced=True)
     .exclude(pk__in=keep).exclude(item__name=IPD_PHARMACY_BILL_ITEM).delete())
    sync_ipd_pharmacy_charge(bill, admission)


def totals(bill, admission):
    """(gross, advances qs, total_advance, net) for an admission's bill."""
    gross = sum((i.total for i in bill.items.all()), Decimal("0"))
    advances = admission.advances.order_by("date")
    total_advance = sum((a.amount for a in advances), Decimal("0"))
    return gross, advances, total_advance, gross - bill.discount - total_advance
