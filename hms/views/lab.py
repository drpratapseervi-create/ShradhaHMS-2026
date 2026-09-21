from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.db import transaction
from django.db.models import Q
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.utils import timezone

from ..decorators import role_required
from ..models import (
    Patient, Consultation, Investigation, InvestigationCategory,
    InvestigationBill, InvestigationBillItem, InvestigationResult,
    InvestigationParameter,
)
from ..utils import render_to_pdf
from ..services.whatsapp import send_lab_report_pdf, WhatsAppSendError
from ._shared import logger


def amount_in_words(number):
    ones = (
        "", "One", "Two", "Three", "Four", "Five", "Six",
        "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve",
        "Thirteen", "Fourteen", "Fifteen", "Sixteen",
        "Seventeen", "Eighteen", "Nineteen",
    )
    tens = (
        "", "", "Twenty", "Thirty", "Forty", "Fifty",
        "Sixty", "Seventy", "Eighty", "Ninety",
    )

    def convert(n):
        if n < 20:
            return ones[n]
        elif n < 100:
            return tens[n // 10] + (" " + ones[n % 10] if n % 10 else "")
        elif n < 1000:
            return ones[n // 100] + " Hundred" + (
                " " + convert(n % 100) if n % 100 else ""
            )
        elif n < 100000:
            return convert(n // 1000) + " Thousand" + (
                " " + convert(n % 1000) if n % 1000 else ""
            )
        elif n < 10000000:
            return convert(n // 100000) + " Lakh" + (
                " " + convert(n % 100000) if n % 100000 else ""
            )
        else:
            return convert(n // 10000000) + " Crore" + (
                " " + convert(n % 10000000) if n % 10000000 else ""
            )

    return f"{convert(int(number))} Rupees Only"


def compute_flag(value_str, param):
    """Returns 'CR', 'HIGH', 'LOW', or '' based on parameter limits."""
    if param.result_type != "numeric":
        return ""
    try:
        v = float(value_str)
    except (ValueError, TypeError):
        return ""
    if param.critical_low is not None and v < param.critical_low:
        return "CR"
    if param.critical_high is not None and v > param.critical_high:
        return "CR"
    if param.max_value is not None and v > param.max_value:
        return "HIGH"
    if param.min_value is not None and v < param.min_value:
        return "LOW"
    return ""


_LAB_FLAG_LABEL = {"HIGH": "HIGH", "LOW": "LOW", "CR": "CRIT"}


def _lab_num(x):
    """Trim trailing .0 from float range bounds -> '140' not '140.0'."""
    try:
        return f"{float(x):g}"
    except (TypeError, ValueError):
        return str(x)


def _lab_range_str(param, gender):
    if gender == "Female" and param.female_range:
        return param.female_range.strip()
    if gender == "Male" and param.male_range:
        return param.male_range.strip()
    if param.min_value is not None and param.max_value is not None:
        return f"{_lab_num(param.min_value)} - {_lab_num(param.max_value)}"
    if param.min_value is not None:
        return f"> {_lab_num(param.min_value)}"
    if param.max_value is not None:
        return f"< {_lab_num(param.max_value)}"
    return "--"


def _lab_param_code(param, item):
    """LOINC code on the parameter, else the investigation's panel LOINC code, else ''."""
    code = (getattr(param, "loinc_code", "") or "").strip()
    if code:
        return code
    return (getattr(item.investigation, "loinc_panel_code", "") or "").strip()


def _lab_panel_label(param, item):
    grp = (param.group or "").strip()
    if grp:
        return grp.upper()
    try:
        return item.investigation.category.get_dept_code_display().upper()
    except Exception:
        return "INVESTIGATIONS"


LAB_REPORTING_DOCTOR = {"name": "Dr. Pratap Senecha, MS, F.MAS",
                        "title": "Reported & Validated By"}


def build_lab_report_context(item, results):
    """
    Structured context for the plain clinical lab-report template.

    Returns a dict with:
      panels      -> [ {"name": "<DEPT>", "rows": [row, ...]}, ... ]
      meta_rows   -> [ (l_label, l_value, r_label, r_value), ... ]  (borderless 2-col)
      remarks     -> single plain-paragraph string
      sig_left / sig_right   -> {"name": ..., "title": ...}  (real names, no placeholder)

    row = {name, code, method, value, flag ('' | HIGH | LOW | CRIT),
           abnormal (bool), range, units}
    method here is the full descriptive sentence (InvestigationParameter.method_description,
    falling back to the short .method label if no description is set).
    """
    patient = item.bill.patient
    gender  = patient.gender or ""

    try:
        ref_doc = item.bill.consultation.appointment.doctor
    except Exception:
        ref_doc = None

    # ---- group rows by panel, preserving encounter order ----
    panel_order, panel_map = [], {}
    for r in results:
        label = _lab_panel_label(r.parameter, item)
        if label not in panel_map:
            panel_map[label] = []
            panel_order.append(label)
        panel_map[label].append({
            "name":     r.parameter.name.strip(),
            "code":     _lab_param_code(r.parameter, item),      # LOINC or panel code or ''
            "method":   ((r.parameter.method_description or "").strip()
                         or (r.parameter.method or "").strip()),
            "value":    str(r.value).strip(),
            "flag":     _LAB_FLAG_LABEL.get(r.flag or "", ""),
            "abnormal": (r.flag or "") in ("HIGH", "LOW", "CR"),
            "range":    _lab_range_str(r.parameter, gender),
            "units":    (r.parameter.unit or "").strip() or "-",
        })
    panels = [{"name": p, "rows": panel_map[p]} for p in panel_order]

    # ---- metadata (borderless two-column) ----
    created = timezone.localtime(item.bill.created_at) if item.bill.created_at else None
    ts = created.strftime("%d-%b-%Y %I:%M %p") if created else "-"

    last_entered = max((r.entered_at for r in results if r.entered_at), default=None)
    reported_ts = (timezone.localtime(last_entered).strftime("%d-%b-%Y %I:%M %p")
                   if last_entered else "-")

    total_params = InvestigationParameter.objects.filter(
        investigation=item.investigation, show_in_report=True).count()
    if not results:
        status = "Pending"
    elif total_params and len(results) >= total_params:
        status = "Final / Validated"
    else:
        status = "Provisional"

    meta_left = [
        ("Patient ID / UHID", patient.uhid or "-"),
        ("Patient Name",      (patient.full_name or "-").title()),
        ("Age / Gender",      f"{patient.age if patient.age is not None else '-'} / {gender or '-'}"),
        ("Referring Dr",      f"Dr. {ref_doc.full_name}" if ref_doc and ref_doc.full_name else "-"),
    ]
    meta_right = [
        ("Bill No",        f"#{item.bill.id}"),
        ("Collected Time", ts),
        ("Reported Time",  reported_ts),
        ("Report Status",  status),
    ]
    # zip into (left_label, left_value, right_label, right_value) rows for the template
    meta_rows = []
    for i in range(max(len(meta_left), len(meta_right))):
        lk, lv = meta_left[i]  if i < len(meta_left)  else ("", "")
        rk, rv = meta_right[i] if i < len(meta_right) else ("", "")
        meta_rows.append((lk, lv, rk, rv))

    # ---- clinical remarks: one plain paragraph ----
    remarks = ("Computer-generated report; values are for clinical reference only. "
               "Please correlate clinically and consult the treating physician for "
               "interpretation.")
    if any(row["abnormal"] for p in panels for row in p["rows"]):
        remarks = ("One or more parameters fall outside the stated reference range and "
                   "have been flagged. ") + remarks

    # ---- signatures ----
    # Left: fixed lab head (no separate technician record in this system).
    sig_left = dict(LAB_REPORTING_DOCTOR)
    # Right: the referring physician from the report data, when there is one.
    if ref_doc and ref_doc.full_name:
        sig_right = {"name": f"Dr. {ref_doc.full_name}",
                     "title": ref_doc.specialization or "Referring Physician"}
    else:
        sig_right = {"name": "-", "title": "Referring Physician"}

    return {
        "panels":    panels,
        "meta_rows": meta_rows,
        "remarks":   remarks,
        "sig_left":  sig_left,
        "sig_right": sig_right,
    }


@login_required
def lab_billing_direct(request, consultation_id=None):
    consultation = patient = bill = None
    ordered_investigations = []

    bill_id = request.GET.get("bill_id")
    if bill_id:
        bill = get_object_or_404(InvestigationBill, id=bill_id)
        consultation = bill.consultation
        patient = bill.patient
        ordered_investigations = bill.items.values_list("investigation_id", flat=True)
    elif consultation_id:
        consultation = get_object_or_404(Consultation, id=consultation_id)
        patient = consultation.appointment.patient
        ordered_investigations = consultation.investigations.values_list("id", flat=True)

    if request.method == "POST":
        if not patient:
            patient = get_object_or_404(Patient, id=request.POST.get("patient_id"))

        inv_ids      = request.POST.getlist("investigations")
        payment_mode = request.POST.get("payment_mode", "CASH")
        discount     = Decimal(request.POST.get("discount", "0") or "0")

        with transaction.atomic():
            if bill:
                bill.items.all().delete()
                bill.total_amount = 0
                bill.save()
            else:
                bill = InvestigationBill.objects.create(
                    consultation=consultation,
                    patient=patient,
                    paid=False,
                    total_amount=0,
                )

            total = 0
            for inv_id in inv_ids:
                inv = get_object_or_404(Investigation, id=inv_id)
                InvestigationBillItem.objects.create(
                    bill=bill, investigation=inv,
                    price=inv.price, added_by="LAB",
                )
                total += inv.price

            bill.total_amount = total
            bill.discount     = discount
            bill.net_amount   = max(total - discount, Decimal("0"))
            bill.payment_mode = payment_mode
            bill.paid = True
            bill.save()

        return redirect("hms:lab_bill_print", bill_id=bill.id)

    return render(request, "lab/direct_billing.html", {
        "consultation":           consultation,
        "patient":                patient,
        "patients":               Patient.objects.all(),
        "categories":             InvestigationCategory.objects.all(),
        "investigations":         Investigation.objects.filter(is_active=True),
        "ordered_investigations": list(ordered_investigations),
    })


@login_required
def pending_lab_orders(request):
    q = request.GET.get("q", "").strip()
    pending_bills = (
        InvestigationBill.objects
        .filter(paid=False)
        .select_related("patient", "consultation__appointment")
        .prefetch_related("items__investigation")
        .order_by("-created_at")
    )
    if q:
        filters = Q(patient__full_name__icontains=q) | Q(patient__uhid__icontains=q)
        bill_id_query = q.lstrip("#")
        if bill_id_query.isdigit():
            filters |= Q(id=int(bill_id_query))
        pending_bills = pending_bills.filter(filters)

    paginator = Paginator(pending_bills, 10)
    page_obj = paginator.get_page(request.GET.get("page"))
    elided_page_range = list(
        paginator.get_elided_page_range(page_obj.number, on_each_side=2, on_ends=1)
    )
    return render(request, "lab/pending_lab_orders.html", {
        "pending_bills": page_obj,
        "page_obj": page_obj,
        "elided_page_range": elided_page_range,
        "q": q,
    })


@login_required
def lab_mark_paid(request, bill_id):
    bill = get_object_or_404(InvestigationBill, id=bill_id)
    if request.method == "POST":
        bill.paid = True
        bill.payment_mode = request.POST.get("payment_mode", "CASH")
        bill.save()
        messages.success(request, f"Bill #{bill.id} marked as paid.")
    return redirect("hms:pending_lab_orders")


@login_required
@role_required("laboratory", "admin")
def lab_result_entry(request, bill_item_id):
    item = get_object_or_404(InvestigationBillItem, id=bill_item_id)

    if not item.bill.paid:
        messages.error(request, "Cannot enter results for unpaid bill.")
        return redirect("hms:pending_lab_orders")

    parameters = InvestigationParameter.objects.filter(
        investigation=item.investigation
    ).order_by("order")

    existing_results = {
        r.parameter_id: r.value
        for r in InvestigationResult.objects.filter(bill_item=item)
    }

    if request.method == "POST":
        InvestigationResult.objects.filter(bill_item=item).delete()
        results_to_create = []
        for p in parameters:
            value = request.POST.get(f"param_{p.id}", "").strip()
            if value:
                results_to_create.append(
                    InvestigationResult(
                        bill_item=item,
                        parameter=p,
                        value=value,
                        entered_by=request.user.username,
                    )
                )
        if results_to_create:
            InvestigationResult.objects.bulk_create(results_to_create)
            messages.success(request, "Lab results saved successfully.")
        return redirect("hms:lab_report_print", bill_item_id=item.id)

    return render(request, "lab/result_entry.html", {
        "item":             item,
        "parameters":       parameters,
        "existing_results": existing_results,
    })


@login_required
def lab_reports(request):
    completed_items = (
        InvestigationBillItem.objects
        .filter(bill__paid=True)
        .select_related("bill__patient", "investigation")
        .prefetch_related("results")
        .order_by("-bill__created_at")
        .distinct()
    )
    return render(request, "lab/lab_reports.html", {"completed_items": completed_items})


def _lab_report_context(bill_item_id):
    """Shared context for lab/report_print.html -- used by both the
    browser-print view and the WhatsApp-send view so they render identically."""
    item = get_object_or_404(
        InvestigationBillItem.objects.select_related(
            "bill__patient",
            "bill__consultation__appointment__doctor",
            "investigation__category",
        ),
        id=bill_item_id,
    )

    results = list(
        InvestigationResult.objects
        .filter(bill_item=item)
        .select_related("parameter")
        .order_by("parameter__order", "parameter__name")
    )

    for r in results:
        r.flag = compute_flag(r.value, r.parameter)

    ctx = {"item": item, "results": results}
    ctx.update(build_lab_report_context(item, results))
    return item, ctx


@login_required
def lab_report_print(request, bill_item_id):
    _item, ctx = _lab_report_context(bill_item_id)
    return render(request, "lab/report_print.html", ctx)


@login_required
@require_POST
def lab_report_send_whatsapp(request, bill_item_id):
    item, ctx = _lab_report_context(bill_item_id)
    pdf_bytes = render_to_pdf("lab/report_print.html", ctx).content

    try:
        send_lab_report_pdf(item, pdf_bytes)
    except ValueError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=400)
    except WhatsAppSendError:
        logger.exception("Failed to send lab report PDF via WhatsApp for bill_item %s", item.id)
        return JsonResponse({"success": False, "error": "Failed to send via WhatsApp. Please try again."}, status=502)

    return JsonResponse({"success": True})


@login_required
def lab_bill_print(request, bill_id):
    bill  = get_object_or_404(InvestigationBill, id=bill_id)
    items = InvestigationBillItem.objects.filter(bill=bill)
    net_amount_display = bill.net_amount if bill.net_amount else (bill.total_amount - bill.discount)
    return render(request, "lab/lab_bill_print.html", {
        "bill":                bill,
        "items":               items,
        "amount_in_words":     amount_in_words(bill.total_amount),
        "net_amount_display":  net_amount_display,
    })

