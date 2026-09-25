from decimal import Decimal
from datetime import date, datetime, time

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone

from ..models import (
    Patient, Doctor, Department, IPDAdmission, BillItem, DischargeBill,
    DischargeBillItem, IPDAdvance, ProcedureItem, ProcedureBill, ProcedureBillItem,
)
from ..ipd.billing import get_bill, sync_bill, totals, ward_charge_item_ids
from ..pharmacy.dispensing import IPD_PHARMACY_BILL_ITEM
from ..services.whatsapp import send_discharge_thankyou, WhatsAppSendError
from ..abdm.services.hip import HIPService
from ._shared import logger


def _current_admission(patient):
    """The admission a patient-based link means: the open one, else the latest real one."""
    admissions = IPDAdmission.objects.filter(patient=patient).exclude(status="CANCELLED")
    return admissions.filter(status="ADMITTED").order_by("-admission_date").first() \
        or admissions.order_by("-admission_date").first()


@login_required
def discharge_bill(request, patient_id):
    """Old patient-based entry point: open the bill of the patient's current admission."""
    patient = get_object_or_404(Patient, id=patient_id)
    admission = _current_admission(patient)
    if not admission:
        return render(request, "ipd/discharge_bill.html", {
            "error": "No admission found for this patient.",
            "patient": patient,
        })
    return redirect("hms:admission_bill", admission_id=admission.id)


@login_required
def admission_bill(request, admission_id):
    admission = get_object_or_404(IPDAdmission.objects.select_related("patient", "bed__ward"), id=admission_id)
    patient = admission.patient
    if admission.status == "CANCELLED":
        return render(request, "ipd/discharge_bill.html", {
            "error": f"{admission.ipd_no} was cancelled (entered in error); it has no bill.",
            "patient": patient,
        })

    bill = get_bill(admission)
    sync_bill(bill, admission)

    if request.method == "POST":
        action = request.POST.get("action")
        if bill.is_paid and action in ("add_item", "update_payment", "mark_paid"):
            messages.error(request, "This bill is already paid and can't be changed.")
            return redirect("hms:admission_bill", admission_id=admission.id)

        if action == "add_item":
            item = get_object_or_404(BillItem, id=request.POST.get("item"))
            qty  = int(request.POST.get("quantity", 1))
            line = DischargeBillItem.objects.filter(bill=bill, item=item).first()
            if line:
                line.quantity += qty
            else:
                line = DischargeBillItem.objects.create(bill=bill, item=item, quantity=qty, price=item.price, total=0)
            line.total = line.quantity * line.price
            line.save()

        elif action == "update_payment":
            bill.discount = Decimal(request.POST.get("discount", "0") or "0")
            bill.save()

        elif action == "add_advance":
            amount = Decimal(request.POST.get("advance_amount", "0") or "0")
            if amount > 0:
                advance = IPDAdvance.objects.create(
                    patient=patient, admission=admission, amount=amount,
                    payment_mode=request.POST.get("advance_payment_mode", "CASH"),
                    note=request.POST.get("advance_note", ""),
                )
                return redirect("hms:advance_payment_receipt_single", advance_id=advance.id)

        elif action == "mark_paid":
            # The day the money was actually received: the daily report counts it on that day.
            today = timezone.localdate()
            try:
                paid_on = datetime.strptime(request.POST.get("paid_on", ""), "%Y-%m-%d").date()
            except ValueError:
                paid_on = today
            if not (timezone.localtime(admission.admission_date).date() <= paid_on <= today):
                messages.error(request, "The payment date must be between the admission date and today.")
                return redirect("hms:admission_bill", admission_id=admission.id)

            gross, _, total_advance, net = totals(bill, admission)
            bill.total_amount  = gross
            bill.advance_paid  = total_advance
            bill.payment_mode  = request.POST.get("final_payment_mode", "CASH")
            bill.final_amount  = max(net, Decimal("0"))
            bill.is_paid       = True
            bill.paid_at       = timezone.now() if paid_on == today else timezone.make_aware(
                datetime.combine(paid_on, time(12, 0)), timezone.get_current_timezone())
            bill.save()

            # ── Billing complete → send the discharge thank-you WhatsApp
            # message once, the same fire-and-forget pattern as the OPD
            # visit thank-you message (a WhatsApp failure must not block
            # the receipt). Skipped for a payment entered after the fact. ──
            if paid_on == today and not admission.discharge_message_sent_at:
                try:
                    send_discharge_thankyou(admission)
                except (WhatsAppSendError, ValueError):
                    logger.exception(
                        "Failed to send discharge thank-you WhatsApp message for admission %s",
                        admission.id,
                    )
                else:
                    admission.discharge_message_sent_at = timezone.now()
                    admission.save(update_fields=["discharge_message_sent_at"])
                HIPService.notify_discharge_summary(admission)

            return redirect("hms:admission_final_receipt", admission_id=admission.id)

        return redirect("hms:admission_bill", admission_id=admission.id)

    bill_items = DischargeBillItem.objects.filter(bill=bill).select_related("item")
    total_amount, advances, total_advance, net = totals(bill, admission)
    if not bill.is_paid:
        bill.total_amount, bill.advance_paid, bill.final_amount = total_amount, total_advance, net
        bill.save(update_fields=["total_amount", "advance_paid", "final_amount"])

    auto_item_ids = ward_charge_item_ids()
    return render(request, "ipd/discharge_bill.html", {
        "patient":       patient,
        "admission":     admission,
        # Bed charges and the pharmacy line are added automatically; keep them out of the manual list.
        "items":         BillItem.objects.exclude(name=IPD_PHARMACY_BILL_ITEM).exclude(id__in=auto_item_ids),
        "bill_items":    bill_items,
        "total_amount":  total_amount,
        "bill":          bill,
        "net_amount":    max(net, 0),
        "refund_amount": abs(net) if net < 0 else 0,
        "advances":      advances,
        "total_advance": total_advance,
        "ipd_pharmacy_item_name": IPD_PHARMACY_BILL_ITEM,
        "can_discharge_with_dues": request.user.is_superuser or getattr(getattr(request.user, "profile", None), "role", "") == "admin",
    })


@login_required
def delete_bill_item(request, item_id):
    item = get_object_or_404(DischargeBillItem.objects.select_related("bill"), id=item_id)
    admission_id = item.bill.admission_id
    if item.bill.is_paid:
        messages.error(request, "This bill is already paid and can't be changed.")
    else:
        item.delete()
    return redirect("hms:admission_bill", admission_id=admission_id)


@login_required
def discharge_bill_pdf(request, admission_id):
    admission = get_object_or_404(IPDAdmission, id=admission_id)
    patient   = admission.patient
    bill      = get_bill(admission)
    sync_bill(bill, admission)
    bill_items = DischargeBillItem.objects.filter(bill=bill)
    total_amount, advances, total_advance, net = totals(bill, admission)
    return render(request, "ipd/discharge_bill_pdf.html", {
        "patient":       patient,
        "admission":     admission,
        "bill_items":    bill_items,
        "total_amount":  total_amount,
        "bill":          bill,
        "advances":      advances,
        "total_advance": total_advance,
        "discount":      bill.discount,
        "net_amount":    max(net, 0),
        "refund_amount": abs(net) if net < 0 else 0,
    })


@login_required
def advance_payment_receipt(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    admission = _current_admission(patient)
    if not admission:
        messages.error(request, "No admission found for this patient.")
        return redirect("hms:dashboard")
    return redirect("hms:admission_advance_receipt", admission_id=admission.id)


@login_required
def admission_advance_receipt(request, admission_id):
    admission = get_object_or_404(IPDAdmission.objects.select_related("patient"), id=admission_id)
    bill = get_bill(admission)
    gross, advances, total_advance, net = totals(bill, admission)
    return render(request, "ipd/advance_payment_receipt.html", {
        "patient":       admission.patient,
        "admission":     admission,
        "bill":          bill,
        "now":           timezone.now(),
        "net_amount":    max(net, 0),
        "refund_amount": abs(net) if net < 0 else 0,
        "receipt_no":    f"ADV-{bill.id:05d}",
        "gross_total":   gross,
        "advances":      advances,
        "total_advance": total_advance,
    })


@login_required
def advance_payment_receipt_single(request, advance_id):
    advance   = get_object_or_404(IPDAdvance, id=advance_id)
    patient   = advance.patient
    admission = advance.admission or _current_admission(patient)
    bill      = DischargeBill.objects.filter(admission=admission).first() if admission else None
    if bill and admission:
        gross, _, total_advance, net = totals(bill, admission)
        discount = bill.discount
    else:
        gross, total_advance, discount = Decimal("0"), advance.amount, Decimal("0")
        net = -total_advance
    return render(request, "ipd/advance_payment_receipt_single.html", {
        "patient":       patient,
        "admission":     admission,
        "bill":          bill,
        "advance":       advance,
        "receipt_no":    f"ADV-{advance.pk:05d}",
        "now":           advance.date,
        "net_amount":    max(net, 0),
        "refund_amount": abs(net) if net < 0 else 0,
        "gross_total":   gross,
        "total_advance": total_advance,
    })


@login_required
def final_payment_receipt(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    admission = _current_admission(patient)
    if not admission:
        messages.error(request, "No admission found for this patient.")
        return redirect("hms:dashboard")
    return redirect("hms:admission_final_receipt", admission_id=admission.id)


@login_required
def admission_final_receipt(request, admission_id):
    admission = get_object_or_404(IPDAdmission.objects.select_related("patient"), id=admission_id)
    bill = get_object_or_404(DischargeBill, admission=admission)
    bill_items = DischargeBillItem.objects.filter(bill=bill)
    gross, advances, total_advance, net = totals(bill, admission)
    return render(request, "ipd/final_payment_receipt.html", {
        "patient":        admission.patient,
        "admission":      admission,
        "bill":           bill,
        "bill_items":     bill_items,
        "gross":          gross,
        "net_amount":     max(net, Decimal("0")),
        "refund_amount":  abs(net) if net < 0 else Decimal("0"),
        "receipt_no":     f"FPR-{bill.id:05d}",
        "advances_count": advances.count(),
        "now":            bill.paid_at or timezone.now(),
    })


@login_required
def procedure_billing(request):
    patients    = Patient.objects.all().order_by("-id")[:100]
    procedures  = ProcedureItem.objects.filter(is_active=True)
    departments = Department.objects.all()
    doctors     = Doctor.objects.select_related("department")

    if request.method == "POST":
        patient_id    = request.POST.get("patient_id")
        department_id = request.POST.get("department_id") or None
        doctor_id     = request.POST.get("doctor_id") or None
        payment_mode  = request.POST.get("payment_mode", "CASH")
        discount      = request.POST.get("discount", "0") or "0"
        procedure_ids = [pid for pid in request.POST.getlist("procedures") if pid.isdigit()]

        errors = []
        if not patient_id:
            errors.append("Please select a patient.")
        if not procedure_ids:
            errors.append("Please select at least one procedure.")

        if errors:
            for e in errors:
                messages.error(request, e)
        else:
            patient    = get_object_or_404(Patient, id=patient_id)
            department = Department.objects.filter(id=department_id).first() if department_id else None
            doctor     = Doctor.objects.filter(id=doctor_id).first() if doctor_id else None
            discount   = Decimal(discount)
            selected   = ProcedureItem.objects.filter(id__in=procedure_ids)
            total      = sum((p.price for p in selected), Decimal("0"))
            net        = max(total - discount, Decimal("0"))

            bill = ProcedureBill.objects.create(
                patient=patient,
                department=department,
                consultant=doctor,
                payment_mode=payment_mode,
                total_amount=total,
                discount=discount,
                net_amount=net,
                created_by=request.user,
            )

            for proc in selected:
                ProcedureBillItem.objects.create(
                    bill=bill,
                    procedure=proc,
                    price=proc.price,
                )

            messages.success(request, f"Bill generated for {patient.full_name}")
            return redirect("hms:procedure_bill_print", bill_id=bill.id)

    return render(request, "billing/procedure_billing.html", {
        "patients":    patients,
        "procedures":  procedures,
        "departments": departments,
        "doctors":     doctors,
    })


@login_required
def procedure_bill_print(request, bill_id):
    bill = get_object_or_404(
        ProcedureBill.objects.select_related(
            "patient", "consultant", "department"
        ).prefetch_related("items__procedure"),
        id=bill_id
    )
    return render(request, "billing/procedure_bill_print.html", {"bill": bill})


def procedure_pending_list(request):
    bills = ProcedureBill.objects.all().order_by('-id')
    return render(request, "billing/procedure_pending.html", {
        "bills": bills
    })

