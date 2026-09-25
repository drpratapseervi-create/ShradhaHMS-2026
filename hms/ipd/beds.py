"""
Admission, transfer and discharge: the only places that should change bed occupancy.
Each stay in a bed is a BedStay, so bed charges follow the ward the patient was in.
"""

from django.db import transaction
from django.utils import timezone

from hms.models import Bed, BedStay, DischargeBill, IPDAdmission


class BedUnavailable(Exception):
    pass


class AlreadyAdmitted(Exception):
    def __init__(self, admission):
        self.admission = admission
        super().__init__(f"{admission.patient.full_name} is already admitted ({admission.ipd_no}).")


class DischargeBlocked(Exception):
    pass


def open_admission(patient):
    return IPDAdmission.objects.filter(patient=patient, status="ADMITTED").order_by("-admission_date").first()


def _lock_bed(bed):
    return Bed.objects.select_for_update().select_related("ward").get(pk=bed.pk)


@transaction.atomic
def admit(*, patient, bed, doctor=None, admission_date=None, **fields):
    """Create an admission in a free bed. Raises BedUnavailable / AlreadyAdmitted."""
    if bed is None:
        raise BedUnavailable("Choose a bed.")
    bed = _lock_bed(bed)
    if not bed.is_available:
        raise BedUnavailable(f"{bed} is not available ({'occupied' if bed.is_occupied else bed.get_housekeeping_display()}).")
    existing = open_admission(patient)
    if existing:
        raise AlreadyAdmitted(existing)

    when = admission_date or timezone.now()
    admission = IPDAdmission.objects.create(
        patient=patient, doctor=doctor, department=getattr(doctor, "department", None) if doctor else None,
        ward=bed.ward, bed=bed, admission_date=when, status="ADMITTED", **fields,
    )
    BedStay.objects.create(admission=admission, bed=bed, ward=bed.ward, start=when)
    bed.is_occupied = True
    bed.save(update_fields=["is_occupied"])
    return admission


def _close_current_stay(admission, when):
    stay = admission.bed_stays.filter(end__isnull=True).order_by("-start").first()
    if stay:
        stay.end = max(when, stay.start)
        stay.save(update_fields=["end"])
    return stay


def _release_bed(bed_id):
    if bed_id:
        Bed.objects.filter(pk=bed_id).update(is_occupied=False, housekeeping="CLEANING")


@transaction.atomic
def transfer(admission, new_bed, *, when=None):
    admission = IPDAdmission.objects.select_for_update().get(pk=admission.pk)
    if admission.status != "ADMITTED":
        raise BedUnavailable(f"{admission.ipd_no} is not admitted.")
    new_bed = _lock_bed(new_bed)
    if new_bed.pk == admission.bed_id:
        raise BedUnavailable("The patient is already in that bed.")
    if not new_bed.is_available:
        raise BedUnavailable(f"{new_bed} is not available.")
    when = when or timezone.now()
    old_bed_id = admission.bed_id
    _close_current_stay(admission, when)
    # First bed for an admission that never had one: bill it from admission, not from now.
    start = admission.admission_date if not admission.bed_stays.exists() else when
    BedStay.objects.create(admission=admission, bed=new_bed, ward=new_bed.ward, start=start)
    _release_bed(old_bed_id)
    new_bed.is_occupied = True
    new_bed.save(update_fields=["is_occupied"])
    admission.bed, admission.ward = new_bed, new_bed.ward
    admission.save(update_fields=["bed", "ward"])
    return admission


@transaction.atomic
def discharge(admission, *, user, when=None, override_reason=""):
    """
    Close the admission and free its bed (to Cleaning). The discharge bill must be
    paid, unless an admin gives a reason (recorded on the admission).
    """
    admission = IPDAdmission.objects.select_for_update().get(pk=admission.pk)
    if admission.status != "ADMITTED":
        raise DischargeBlocked(f"{admission.ipd_no} is not admitted.")
    bill = DischargeBill.objects.filter(admission=admission).first()
    if not (bill and bill.is_paid):
        is_admin = user.is_superuser or getattr(getattr(user, "profile", None), "role", "") == "admin"
        if not (is_admin and override_reason.strip()):
            raise DischargeBlocked("The discharge bill is not paid. Only an admin can discharge with dues, and must give a reason.")
    when = when or timezone.now()
    if when < admission.admission_date or when > timezone.now():
        raise DischargeBlocked("The discharge time must be between the admission time and now.")
    _close_current_stay(admission, when)
    _release_bed(admission.bed_id)
    admission.status = "DISCHARGED"
    admission.discharge_date = when
    admission.discharged_by = user
    admission.discharge_override_reason = override_reason.strip()[:200] if not (bill and bill.is_paid) else ""
    admission.save(update_fields=["status", "discharge_date", "discharged_by", "discharge_override_reason"])
    return admission


@transaction.atomic
def cancel_admission(admission, *, user, reason):
    """For admissions entered in error (duplicates): only allowed while nothing was charged against them."""
    admission = IPDAdmission.objects.select_for_update().get(pk=admission.pk)
    if admission.status == "CANCELLED":
        return admission
    if admission.pharmacy_bills.filter(status="PAID").exists() or admission.advances.exists() \
            or DischargeBill.objects.filter(admission=admission, is_paid=True).exists():
        raise DischargeBlocked(f"{admission.ipd_no} has charges or payments; discharge it instead of cancelling.")
    now = timezone.now()
    _close_current_stay(admission, now)
    if admission.bed_id and admission.status == "ADMITTED":
        Bed.objects.filter(pk=admission.bed_id).update(is_occupied=False)
    admission.status = "CANCELLED"
    admission.discharged_by = user
    admission.discharge_override_reason = f"Cancelled: {reason}"[:200]
    admission.save(update_fields=["status", "discharged_by", "discharge_override_reason"])
    return admission


# ── Day counting: nights stayed, minimum 1 (hospital policy, 2026-09-25) ──

def _local_date(dt):
    return timezone.localtime(dt).date()


def stay_end(admission):
    """Billing runs to the discharge time once discharged, otherwise to now."""
    if admission.status == "DISCHARGED" and admission.discharge_date:
        return admission.discharge_date
    return timezone.now()


def billable_days(admission):
    return max(1, (_local_date(stay_end(admission)) - _local_date(admission.admission_date)).days)


def bed_charge_nights(admission):
    """
    [(Ward, nights)] per stay, nights by the same rule. Stays telescope, so the nights
    add up to billable_days(); a same-day admit+discharge charges 1 night to the last ward.
    """
    end = stay_end(admission)
    stays = list(admission.bed_stays.select_related("ward__bed_charge_item"))
    rows = []
    for s in stays:
        s_end = s.end or end
        rows.append([s.ward, max(0, (_local_date(s_end) - _local_date(s.start)).days)])
    if rows and sum(n for _, n in rows) == 0:
        rows[-1][1] = 1
    return [(w, n) for w, n in rows if n > 0]
