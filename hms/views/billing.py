from decimal import Decimal
from datetime import date

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone

from ..models import (
    Patient, Doctor, Department, IPDAdmission, BillItem, DischargeBill,
    DischargeBillItem, IPDAdvance, ProcedureItem, ProcedureBill, ProcedureBillItem,
)
from ..services.whatsapp import send_discharge_thankyou, WhatsAppSendError
from ..abdm.services.hip import HIPService
from ._shared import logger


@login_required
def discharge_bill(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)

    admission = IPDAdmission.objects.filter(
        patient=patient,
        status="ADMITTED"
    ).order_by("-id").first()

    if not admission:
        return render(request, "ipd/discharge_bill.html", {
            "error": "No active admission found for this patient.",
            "patient": patient,
        })

    bill, created = DischargeBill.objects.get_or_create(
        patient=patient,
        defaults={
            "total_amount": 0,
            "discount": 0,
            "advance_paid": 0,
            "final_amount": 0
        }
    )

    days = (date.today() - admission.admission_date.date()).days
    if days <= 0:
        days = 1

    ward_name = admission.bed.ward.name.split("(")[0].strip()

    def sync_daily_charge(search_name, ward_filter=None):
        query = BillItem.objects.filter(name__icontains=search_name)
        if ward_filter:
            query = query.filter(name__icontains=ward_filter)
        item = query.first()
        if not item:
            return
        line = DischargeBillItem.objects.filter(bill=bill, item=item).first()
        if line:
            line.quantity = days
            line.price    = item.price
            line.total    = item.price * days
            line.save()
        else:
            DischargeBillItem.objects.create(
                bill=bill, item=item,
                quantity=days, price=item.price,
                total=item.price * days
            )

    sync_daily_charge("Bed Charge", ward_name)
    sync_daily_charge("Nursing")
    sync_daily_charge("Consultation")

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add_item":
            item_id = request.POST.get("item")
            qty     = int(request.POST.get("quantity", 1))
            item    = get_object_or_404(BillItem, id=item_id)
            line    = DischargeBillItem.objects.filter(bill=bill, item=item).first()
            if line:
                line.quantity += qty
            else:
                line = DischargeBillItem.objects.create(
                    bill=bill, item=item,
                    quantity=qty, price=item.price, total=0
                )
            line.total = line.quantity * line.price
            line.save()

        elif action == "update_payment":
            discount      = Decimal(request.POST.get("discount", "0") or "0")
            bill.discount = discount
            bill.save()

        elif action == "add_advance":
            amount       = Decimal(request.POST.get("advance_amount", "0") or "0")
            payment_mode = request.POST.get("advance_payment_mode", "CASH")
            note         = request.POST.get("advance_note", "")
            if amount > 0:
                advance = IPDAdvance.objects.create(
                    patient=patient,
                    amount=amount,
                    payment_mode=payment_mode,
                    note=note
                )
                return redirect("hms:advance_payment_receipt_single", advance_id=advance.id)

        elif action == "mark_paid":
            payment_mode   = request.POST.get("final_payment_mode", "CASH")
            advances       = IPDAdvance.objects.filter(patient=patient)
            total_advance  = sum(a.amount for a in advances)
            bill_items_now = DischargeBillItem.objects.filter(bill=bill)
            gross          = sum(i.total for i in bill_items_now)
            net            = gross - bill.discount - total_advance
            bill.advance_paid  = total_advance
            bill.payment_mode  = payment_mode
            bill.final_amount  = max(net, Decimal("0"))
            bill.is_paid       = True
            bill.paid_at       = timezone.now()
            bill.save()

            # ── Billing complete → send the discharge thank-you WhatsApp
            # message once, the same fire-and-forget pattern as the OPD
            # visit thank-you message (a WhatsApp failure must not block
            # the receipt) ──
            if not admission.discharge_message_sent_at:
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

            return redirect("hms:final_payment_receipt", patient_id=patient.id)

        return redirect("hms:discharge_bill", patient_id=patient.id)

    bill_items    = DischargeBillItem.objects.filter(bill=bill)
    total_amount  = sum(i.total for i in bill_items)
    advances      = IPDAdvance.objects.filter(patient=patient).order_by("date")
    total_advance = sum(a.amount for a in advances)
    net           = total_amount - bill.discount - total_advance

    bill.total_amount  = total_amount
    bill.advance_paid  = total_advance
    bill.final_amount  = net
    bill.save()

    return render(request, "ipd/discharge_bill.html", {
        "patient":       patient,
        "admission":     admission,
        "items":         BillItem.objects.all(),
        "bill_items":    bill_items,
        "total_amount":  total_amount,
        "bill":          bill,
        "net_amount":    max(net, 0),
        "refund_amount": abs(net) if net < 0 else 0,
        "advances":      advances,
        "total_advance": total_advance,
    })


@login_required
def delete_bill_item(request, item_id):
    item       = get_object_or_404(DischargeBillItem, id=item_id)
    patient_id = item.bill.patient.id
    item.delete()
    return redirect("hms:discharge_bill", patient_id=patient_id)


@login_required
def discharge_bill_pdf(request, admission_id):
    admission    = get_object_or_404(IPDAdmission, id=admission_id)
    patient      = admission.patient
    bill         = DischargeBill.objects.get(patient=patient)
    bill_items   = DischargeBillItem.objects.filter(bill=bill)
    total_amount = sum(i.total for i in bill_items)
    bill.refresh_from_db()
    advances      = IPDAdvance.objects.filter(patient=patient).order_by("date")
    total_advance = sum(a.amount for a in advances)
    discount      = bill.discount
    net           = total_amount - discount - total_advance
    net_amount    = max(net, 0)
    refund_amount = abs(net) if net < 0 else 0
    return render(request, "ipd/discharge_bill_pdf.html", {
        "patient":       patient,
        "admission":     admission,
        "bill_items":    bill_items,
        "total_amount":  total_amount,
        "bill":          bill,
        "advances":      advances,
        "total_advance": total_advance,
        "discount":      discount,
        "net_amount":    net_amount,
        "refund_amount": refund_amount,
    })


@login_required
def advance_payment_receipt(request, patient_id):
    patient   = get_object_or_404(Patient, id=patient_id)
    admission = IPDAdmission.objects.filter(
        patient=patient, status="ADMITTED"
    ).order_by("-id").first()
    bill          = get_object_or_404(DischargeBill, patient=patient)
    bill_items    = DischargeBillItem.objects.filter(bill=bill)
    gross         = sum(i.total for i in bill_items)
    advances      = IPDAdvance.objects.filter(patient=patient).order_by("date")
    total_advance = sum(a.amount for a in advances)
    net           = gross - bill.discount - total_advance
    net_amount    = max(net, 0)
    refund_amount = abs(net) if net < 0 else 0
    receipt_no    = f"ADV-{bill.id:05d}"
    return render(request, "ipd/advance_payment_receipt.html", {
        "patient":       patient,
        "admission":     admission,
        "bill":          bill,
        "now":           timezone.now(),
        "net_amount":    net_amount,
        "refund_amount": refund_amount,
        "receipt_no":    receipt_no,
        "gross_total":   gross,
        "advances":      advances,
        "total_advance": total_advance,
    })


@login_required
def advance_payment_receipt_single(request, advance_id):
    advance   = get_object_or_404(IPDAdvance, id=advance_id)
    patient   = advance.patient
    admission = IPDAdmission.objects.filter(
        patient=patient, status="ADMITTED"
    ).order_by("-id").first()
    bill          = DischargeBill.objects.filter(patient=patient).first()
    bill_items    = DischargeBillItem.objects.filter(bill=bill) if bill else []
    gross         = sum(i.total for i in bill_items)
    advances      = IPDAdvance.objects.filter(patient=patient).order_by("date")
    total_advance = sum(a.amount for a in advances)
    discount      = bill.discount if bill else 0
    net           = gross - discount - total_advance
    net_amount    = max(net, 0)
    refund_amount = abs(net) if net < 0 else 0
    receipt_no    = f"ADV-{advance.pk:05d}"
    return render(request, "ipd/advance_payment_receipt_single.html", {
        "patient":       patient,
        "admission":     admission,
        "bill":          bill,
        "advance":       advance,
        "receipt_no":    receipt_no,
        "now":           advance.date,
        "net_amount":    net_amount,
        "refund_amount": refund_amount,
        "gross_total":   gross,
        "total_advance": total_advance,
    })


@login_required
def final_payment_receipt(request, patient_id):
    patient   = get_object_or_404(Patient, id=patient_id)
    admission = IPDAdmission.objects.filter(patient=patient).order_by("-id").first()
    bill      = get_object_or_404(DischargeBill, patient=patient)
    bill_items    = DischargeBillItem.objects.filter(bill=bill)
    gross         = sum(i.total for i in bill_items)
    advances      = IPDAdvance.objects.filter(patient=patient).order_by("date")
    total_advance = sum(a.amount for a in advances)
    bill.advance_paid = total_advance
    bill.save()
    net           = gross - bill.discount - total_advance
    net_amount    = max(net, Decimal("0"))
    refund_amount = abs(net) if net < 0 else Decimal("0")
    receipt_no    = f"FPR-{bill.id:05d}"
    return render(request, "ipd/final_payment_receipt.html", {
        "patient":        patient,
        "admission":      admission,
        "bill":           bill,
        "bill_items":     bill_items,
        "gross":          gross,
        "net_amount":     net_amount,
        "refund_amount":  refund_amount,
        "receipt_no":     receipt_no,
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

