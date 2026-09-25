from django.db import migrations

# Ward -> per-day bed charge item, as confirmed by the hospital (2026-09-25).
WARD_RATES = {
    "male ward":    "General Ward Charges (per day)",
    "female ward":  "General Ward Charges (per day)",
    "semi delux a": "Semi-Private Room Charges (per day)",
    "semi delux b": "Semi-Private Room Charges (per day)",
    "a/c room":     "Private Room Charges (per day)",
    "post op ward": "Post-Operative Room Charges (per day)",
}


def _admission_for(admissions, patient_id, when):
    """The patient's latest admission that started on or before `when` (else their latest)."""
    mine = [a for a in admissions if a.patient_id == patient_id]
    before = [a for a in mine if a.admission_date <= when]
    pool = before or mine
    return max(pool, key=lambda a: a.admission_date) if pool else None


def forwards(apps, schema_editor):
    Ward = apps.get_model("hms", "Ward")
    BillItem = apps.get_model("hms", "BillItem")
    IPDAdmission = apps.get_model("hms", "IPDAdmission")
    BedStay = apps.get_model("hms", "BedStay")
    DischargeBill = apps.get_model("hms", "DischargeBill")
    IPDAdvance = apps.get_model("hms", "IPDAdvance")

    items = {i.name.lower(): i for i in BillItem.objects.all()}
    for ward in Ward.objects.all():
        item_name = WARD_RATES.get(ward.name.strip().lower())
        if item_name and item_name.lower() in items:
            ward.bed_charge_item = items[item_name.lower()]
            ward.save(update_fields=["bed_charge_item"])

    admissions = list(IPDAdmission.objects.all())
    for a in admissions:
        if a.bed_id:
            BedStay.objects.create(
                admission=a, bed_id=a.bed_id, ward_id=a.ward_id or a.bed.ward_id, start=a.admission_date,
                end=a.discharge_date if a.status == "DISCHARGED" else None,
            )

    taken = set()
    for bill in DischargeBill.objects.order_by("created_at"):
        a = _admission_for(admissions, bill.patient_id, bill.created_at)
        if a and a.id not in taken:
            bill.admission_id = a.id
            bill.save(update_fields=["admission"])
            taken.add(a.id)

    for adv in IPDAdvance.objects.all():
        a = _admission_for(admissions, adv.patient_id, adv.date)
        if a:
            adv.admission_id = a.id
            adv.save(update_fields=["admission"])


class Migration(migrations.Migration):

    dependencies = [
        ("hms", "0126_bed_ward_management"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
