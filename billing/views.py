# C:\ShradhaHMS_Full\ShradhaHMS_Full\billing\views.py
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import get_template
from django.utils import timezone
from django import forms

from .models import Admission, ChargeItem, AdvancePayment, FinalBill

# -----------------------------
# Forms that MATCH your models
# -----------------------------
class AdmissionForm(forms.ModelForm):
    class Meta:
        model = Admission
        fields = [
            "patient_name",
            "mrn",
            "reg_no",
            "ward",
            "bed",
            "category",
            "doctor",
            "admit_at",
            "discharge_at",
            "remarks",
        ]

class ChargeItemForm(forms.ModelForm):
    class Meta:
        model = ChargeItem
        fields = ["date", "type", "particulars", "qty", "rate", "sac_code"]

class AdvancePaymentForm(forms.ModelForm):
    class Meta:
        model = AdvancePayment
        fields = ["date", "amount", "mode", "ref_no", "note"]

class FinalBillForm(forms.ModelForm):
    class Meta:
        model = FinalBill
        fields = ["discount", "cgst", "sgst", "is_finalized", "remarks"]

# -----------------------------
# Diagnostics
# -----------------------------
def ping(request):
    return HttpResponse("pong ✅ billing is live")

# -----------------------------
# Admissions
# -----------------------------
def admission_list(request):
    qs = Admission.objects.order_by("-id")
    return render(request, "billing/admission_list.html", {"admissions": qs})

def admission_create(request):
    if request.method == "POST":
        form = AdmissionForm(request.POST)
        if form.is_valid():
            ad = form.save()
            return redirect("billing:admission_detail", pk=ad.pk)
    else:
        form = AdmissionForm()
    return render(request, "billing/admission_form.html", {"form": form})

def admission_detail(request, pk):
    ad = get_object_or_404(Admission, pk=pk)
    charges = ad.charges.order_by("-date", "-id")     # related_name="charges"
    advances = ad.advances.order_by("-date", "-id")   # related_name="advances"
    final = getattr(ad, "final_bill", None)           # related_name="final_bill"
    if final is None:
        final = FinalBill.objects.create(admission=ad)
    return render(
        request,
        "billing/admission_detail.html",
        {"ad": ad, "charges": charges, "advances": advances, "final": final},
    )

# -----------------------------
# Add charge / advance
# -----------------------------
def charge_add(request, admission_id):
    ad = get_object_or_404(Admission, pk=admission_id)
    if request.method == "POST":
        form = ChargeItemForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.admission = ad
            obj.save()
            # after save, go to the printable slip
            return redirect("billing:charge_slip", charge_id=obj.id)
    else:
        form = ChargeItemForm(initial={"date": timezone.localdate()})
    return render(request, "billing/charge_form.html", {"ad": ad, "form": form})

def advance_add(request, admission_id):
    ad = get_object_or_404(Admission, pk=admission_id)
    if request.method == "POST":
        form = AdvancePaymentForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.admission = ad
            obj.save()
            # NEW: after save, go straight to the advance slip
            return redirect("billing:advance_slip", advance_id=obj.id)
    else:
        form = AdvancePaymentForm(initial={"date": timezone.localdate()})
    return render(request, "billing/advance_form.html", {"ad": ad, "form": form})

# -----------------------------
# Final bill & summary
# -----------------------------
def finalbill_edit(request, admission_id):
    ad = get_object_or_404(Admission, pk=admission_id)
    final, _ = FinalBill.objects.get_or_create(admission=ad)
    if request.method == "POST":
        form = FinalBillForm(request.POST, instance=final)
        if form.is_valid():
            form.save()
            return redirect("billing:bill_summary", admission_id=ad.id)
    else:
        form = FinalBillForm(instance=final)
    return render(request, "billing/finalbill_form.html", {"ad": ad, "form": form})

def bill_summary(request, admission_id):
    ad = get_object_or_404(Admission, pk=admission_id)
    final, _ = FinalBill.objects.get_or_create(admission=ad)
    charges = list(ad.charges.all())
    advances = list(ad.advances.all())

    subtotal = sum((c.qty * c.rate) for c in charges)
    discount = final.discount or 0
    taxes = (final.cgst or 0) + (final.sgst or 0)
    total_adv = sum(a.amount for a in advances)
    grand_total = max(subtotal - discount + taxes, 0)
    net_payable = max(grand_total - total_adv, 0)

    ctx = {
        "ad": ad,
        "final": final,
        "charges": charges,
        "advances": advances,
        "subtotal": subtotal,
        "discount": discount,
        "taxes": taxes,
        "total_adv": total_adv,
        "grand_total": grand_total,
        "net_payable": net_payable,
    }
    return render(request, "billing/bill_summary.html", ctx)

# -----------------------------
# PDF helpers
# -----------------------------
from xhtml2pdf import pisa
from io import BytesIO

def render_to_pdf(template_path, context):
    """Return (ok: bool, content: bytes) rendered as PDF using xhtml2pdf."""
    html = get_template(template_path).render(context)
    result = BytesIO()
    pdf = pisa.CreatePDF(src=html, dest=result)  # returns error count
    if pdf.err:
        return False, b""
    return True, result.getvalue()

def bill_pdf(request, admission_id):
    ad = get_object_or_404(Admission, pk=admission_id)
    final, _ = FinalBill.objects.get_or_create(admission=ad)
    charges = list(ad.charges.all())
    advances = list(ad.advances.all())

    subtotal = sum((c.qty * c.rate) for c in charges)
    discount = final.discount or 0
    taxes = (final.cgst or 0) + (final.sgst or 0)
    total_adv = sum(a.amount for a in advances)
    grand_total = max(subtotal - discount + taxes, 0)
    net_payable = max(grand_total - total_adv, 0)

    ctx = {
        "ad": ad,
        "final": final,
        "charges": charges,
        "advances": advances,
        "subtotal": subtotal,
        "discount": discount,
        "taxes": taxes,
        "total_adv": total_adv,
        "grand_total": grand_total,
        "net_payable": net_payable,
        "now": timezone.localtime(),
    }
    ok, pdf_bytes = render_to_pdf("billing/bill_summary_pdf.html", ctx)
    if not ok:
        return HttpResponse("PDF generation error", status=500)
    fname = f"IPD_{ad.mrn or ad.id}_final_bill.pdf"
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{fname}"'
    return resp

# -----------------------------
# Single charge slip (HTML & PDF)
# -----------------------------
def charge_slip(request, charge_id):
    """View in browser and print (Ctrl+P)."""
    charge = get_object_or_404(ChargeItem, pk=charge_id)
    ad = charge.admission
    amount = charge.qty * charge.rate
    ctx = {
        "charge": charge,
        "ad": ad,
        "amount": amount,
        "now": timezone.localtime(),
        "hospital_name": "Shradha Hospital, Pali",
        "hospital_addr": "Pani Ki Do Tanki, Surajpole, Pali (Rajasthan)",
        "gstin": "08AAACB0844M1ZV",
        "phone": "94141-22542",
    }
    return render(request, "billing/charge_slip.html", ctx)

def charge_slip_pdf(request, charge_id):
    """Download the same slip as a PDF."""
    charge = get_object_or_404(ChargeItem, pk=charge_id)
    ad = charge.admission
    amount = charge.qty * charge.rate
    ctx = {
        "charge": charge,
        "ad": ad,
        "amount": amount,
        "now": timezone.localtime(),
        "hospital_name": "Shradha Hospital, Pali",
        "hospital_addr": "Pani Ki Do Tanki, Surajpole, Pali (Rajasthan)",
        "gstin": "08AAACB0844M1ZV",
        "phone": "94141-22542",
    }
    ok, pdf_bytes = render_to_pdf("billing/charge_slip.html", ctx)
    if not ok:
        return HttpResponse("PDF generation error", status=500)
    fname = f"charge_{charge.id}_slip.pdf"
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{fname}"'
    return resp

# -----------------------------
# Single advance slip (HTML & PDF)
# -----------------------------
def advance_slip(request, advance_id):
    """View in browser and print (Ctrl+P) for an advance payment."""
    adv = get_object_or_404(AdvancePayment, pk=advance_id)
    ad = adv.admission
    ctx = {
        "advance": adv,
        "ad": ad,
        "now": timezone.localtime(),
        "hospital_name": "Shradha Hospital, Pali",
        "hospital_addr": "Pani Ki Do Tanki, Surajpole, Pali (Rajasthan)",
        "gstin": "08AAACB0844M1ZV",
        "phone": "94141-22542",
    }
    return render(request, "billing/advance_slip.html", ctx)

def advance_slip_pdf(request, advance_id):
    """Download the same advance slip as a PDF."""
    adv = get_object_or_404(AdvancePayment, pk=advance_id)
    ad = adv.admission
    ctx = {
        "advance": adv,
        "ad": ad,
        "now": timezone.localtime(),
        "hospital_name": "Shradha Hospital, Pali",
        "hospital_addr": "Pani Ki Do Tanki, Surajpole, Pali (Rajasthan)",
        "gstin": "08AAACB0844M1ZV",
        "phone": "94141-22542",
    }
    ok, pdf_bytes = render_to_pdf("billing/advance_slip.html", ctx)
    if not ok:
        return HttpResponse("PDF generation error", status=500)
    fname = f"advance_{adv.id}_slip.pdf"
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{fname}"'
    return resp

