from datetime import date
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.db.models import Q, Sum, Count
from django.contrib import messages
from django.contrib.auth.decorators import login_required

from ..decorators import role_required
from ..models import (
    ConstructionExpense, Vendor, ConstructionMedia, PartnerDeposit,
    EXPENSE_HEAD_CHOICES, AREA_CHOICES, PAYMENT_MODE_CHOICES,
    PAID_BY_CHOICES, PAID_FROM_CHOICES, APPROVAL_STATUS_CHOICES,
    APPROVED_BY_CHOICES, WORK_STATUS_CHOICES, YES_NO_PARTIAL_CHOICES,
    INVOICE_TYPE_CHOICES,
)


@login_required
@role_required("admin")
def construction_expense_list(request):
    qs = ConstructionExpense.objects.select_related("vendor").order_by("-created_at")

    head      = request.GET.get("expense_head", "")
    area      = request.GET.get("area_location", "")
    status    = request.GET.get("approval_status", "")
    paid_by   = request.GET.get("paid_by", "")
    date_from = request.GET.get("date_from", "")
    date_to   = request.GET.get("date_to", "")
    q         = request.GET.get("q", "")

    if head:      qs = qs.filter(expense_head=head)
    if area:      qs = qs.filter(area_location=area)
    if status:    qs = qs.filter(approval_status=status)
    if paid_by:   qs = qs.filter(paid_by=paid_by)
    if date_from: qs = qs.filter(date__gte=date_from)
    if date_to:   qs = qs.filter(date__lte=date_to)
    if q:
        qs = qs.filter(
            Q(expense_id__icontains=q) | Q(description__icontains=q) |
            Q(vendor__name__icontains=q) | Q(bill_no__icontains=q)
        )

    totals = qs.aggregate(
        grand_total=Sum("total_amount"),
        total_gst=Sum("gst_amount"),
        count=Count("id"),
    )

    all_media = list(ConstructionMedia.objects.select_related("uploaded_by").order_by("uploaded_at"))
    media_videos   = sorted((m for m in all_media if m.media_type == "video"),    key=lambda m: m.display_date)
    media_photos   = sorted((m for m in all_media if m.media_type == "photo"),    key=lambda m: m.display_date)
    media_documents = sorted((m for m in all_media if m.media_type == "document"), key=lambda m: m.display_date)

    return render(request, "hms/construction/expense_list.html", {
        "expenses": qs,
        "totals": totals,
        "expense_head_choices": EXPENSE_HEAD_CHOICES,
        "area_choices": AREA_CHOICES,
        "approval_status_choices": APPROVAL_STATUS_CHOICES,
        "paid_by_choices": PAID_BY_CHOICES,
        "f_head": head, "f_area": area, "f_status": status,
        "f_paid_by": paid_by, "f_date_from": date_from,
        "f_date_to": date_to, "f_q": q,
        "media_videos": media_videos,
        "media_photos": media_photos,
        "media_documents": media_documents,
        "media_max_size_mb": CONSTRUCTION_MEDIA_MAX_SIZE_MB,
    })


CONSTRUCTION_MEDIA_MAX_SIZE_MB = 500


CONSTRUCTION_MEDIA_ALLOWED_EXTENSIONS = tuple(
    f".{ext}" for ext in
    ['mp4', 'mov', 'avi', 'mkv', 'webm', '3gp', 'jpg', 'jpeg', 'png', 'webp', 'heic',
     'pdf', 'doc', 'docx', 'dwg', 'dxf']
)


@login_required
@role_required("admin")
def construction_media_upload(request):
    if request.method == "POST":
        files = request.FILES.getlist("files")
        caption = request.POST.get("caption", "").strip() or None

        if not files:
            messages.error(request, "Please choose at least one photo or video to upload.")
        else:
            uploaded, skipped = 0, []
            for f in files:
                if not f.name.lower().endswith(CONSTRUCTION_MEDIA_ALLOWED_EXTENSIONS):
                    skipped.append(f"{f.name} (unsupported type)")
                    continue
                if f.size > CONSTRUCTION_MEDIA_MAX_SIZE_MB * 1024 * 1024:
                    skipped.append(f"{f.name} ({f.size / (1024*1024):.0f} MB, over {CONSTRUCTION_MEDIA_MAX_SIZE_MB} MB limit)")
                    continue
                ConstructionMedia.objects.create(
                    file=f,
                    caption=caption,
                    uploaded_by=request.user,
                )
                uploaded += 1

            if uploaded:
                messages.success(request, f"{uploaded} file(s) uploaded successfully.")
            if skipped:
                messages.error(request, "Skipped: " + "; ".join(skipped))

    return redirect("hms:construction_expense_list")


@login_required
@role_required("admin")
def construction_media_delete(request, pk):
    media = get_object_or_404(ConstructionMedia, pk=pk)
    if request.method == "POST":
        media.file.delete(save=False)
        media.delete()
        messages.success(request, "File deleted.")
    return redirect("hms:construction_expense_list")


@login_required
@role_required("admin")
def construction_expense_create(request):
    vendors = Vendor.objects.all().order_by("name")

    if request.method == "POST":
        try:
            vendor_id   = request.POST.get("vendor_id", "").strip()
            vendor_name = request.POST.get("vendor_name", "").strip()
            vendor = None
            if vendor_id:
                vendor = Vendor.objects.filter(pk=vendor_id).first()
            elif vendor_name:
                vendor, _ = Vendor.objects.get_or_create(
                    name=vendor_name,
                    defaults={"mobile": request.POST.get("vendor_mobile", "")}
                )

            expense = ConstructionExpense(
                date              = request.POST.get("date"),
                expense_head      = request.POST.get("expense_head"),
                subcategory       = request.POST.get("subcategory") or None,
                description       = request.POST.get("description"),
                area_location     = request.POST.get("area_location") or None,
                vendor            = vendor,
                vendor_mobile     = request.POST.get("vendor_mobile") or None,
                bill_no           = request.POST.get("bill_no") or None,
                qty               = request.POST.get("qty") or None,
                unit              = request.POST.get("unit") or None,
                rate              = request.POST.get("rate") or None,
                amount            = float(request.POST.get("amount") or 0),
                gst_percent       = float(request.POST.get("gst_percent") or 0),
                payment_mode      = request.POST.get("payment_mode") or None,
                paid_by           = request.POST.get("paid_by") or None,
                paid_from         = request.POST.get("paid_from") or None,
                approval_status   = request.POST.get("approval_status", "Pending"),
                approved_by       = request.POST.get("approved_by") or None,
                work_status       = request.POST.get("work_status") or None,
                material_received = request.POST.get("material_received") or None,
                invoice_type      = request.POST.get("invoice_type") or None,
                balance_due       = request.POST.get("balance_due") or None,
                due_date          = request.POST.get("due_date") or None,
                remarks           = request.POST.get("remarks") or None,
            )
            if request.FILES.get("bill_image"):
                expense.bill_image = request.FILES["bill_image"]
            if request.FILES.get("site_photo"):
                expense.site_photo = request.FILES["site_photo"]
            if request.FILES.get("quotation_file"):
                expense.quotation_file = request.FILES["quotation_file"]

            expense.save()
            messages.success(request, f"Expense {expense.expense_id} saved successfully.")
            return redirect("hms:construction_expense_list")

        except Exception as e:
            messages.error(request, f"Error saving expense: {e}")

    return render(request, "hms/construction/expense_form.html", {"vendors": vendors})


@login_required
@role_required("admin")
def construction_expense_edit(request, pk):
    expense = get_object_or_404(ConstructionExpense, pk=pk)
    vendors = Vendor.objects.all().order_by("name")

    if request.method == "POST":
        try:
            vendor_id   = request.POST.get("vendor_id", "").strip()
            vendor_name = request.POST.get("vendor_name", "").strip()
            vendor = None
            if vendor_id:
                vendor = Vendor.objects.filter(pk=vendor_id).first()
            elif vendor_name:
                vendor, _ = Vendor.objects.get_or_create(
                    name=vendor_name,
                    defaults={"mobile": request.POST.get("vendor_mobile", "")}
                )

            expense.date              = request.POST.get("date")
            expense.expense_head      = request.POST.get("expense_head")
            expense.subcategory       = request.POST.get("subcategory") or None
            expense.description       = request.POST.get("description")
            expense.area_location     = request.POST.get("area_location") or None
            expense.vendor            = vendor
            expense.vendor_mobile     = request.POST.get("vendor_mobile") or None
            expense.bill_no           = request.POST.get("bill_no") or None
            expense.qty               = request.POST.get("qty") or None
            expense.unit              = request.POST.get("unit") or None
            expense.rate              = request.POST.get("rate") or None
            expense.amount            = float(request.POST.get("amount") or 0)
            expense.gst_percent       = float(request.POST.get("gst_percent") or 0)
            expense.payment_mode      = request.POST.get("payment_mode") or None
            expense.paid_by           = request.POST.get("paid_by") or None
            expense.paid_from         = request.POST.get("paid_from") or None
            expense.approval_status   = request.POST.get("approval_status", "Pending")
            expense.approved_by       = request.POST.get("approved_by") or None
            expense.work_status       = request.POST.get("work_status") or None
            expense.material_received = request.POST.get("material_received") or None
            expense.invoice_type      = request.POST.get("invoice_type") or None
            expense.balance_due       = request.POST.get("balance_due") or None
            expense.due_date          = request.POST.get("due_date") or None
            expense.remarks           = request.POST.get("remarks") or None

            if request.FILES.get("bill_image"):
                expense.bill_image = request.FILES["bill_image"]
            if request.FILES.get("site_photo"):
                expense.site_photo = request.FILES["site_photo"]
            if request.FILES.get("quotation_file"):
                expense.quotation_file = request.FILES["quotation_file"]

            expense.save()
            messages.success(request, f"Expense {expense.expense_id} updated.")
            return redirect("hms:construction_expense_list")

        except Exception as e:
            messages.error(request, f"Error updating: {e}")

    ctx = {"vendors": vendors}
    ctx.update({"expense": expense, "edit_mode": True})
    return render(request, "hms/construction/expense_form.html", ctx)


@login_required
@role_required("admin")
def construction_expense_delete(request, pk):
    expense = get_object_or_404(ConstructionExpense, pk=pk)
    if request.method == "POST":
        eid = expense.expense_id
        expense.delete()
        messages.success(request, f"Expense {eid} deleted.")
    return redirect("hms:construction_expense_list")


@login_required
def construction_expense_receipt(request, pk):
    expense = get_object_or_404(ConstructionExpense, pk=pk)
    return render(request, "hms/construction/expense_receipt.html", {"expense": expense})


@login_required
def vendor_search_ajax(request):
    q = request.GET.get("q", "")
    vendors = Vendor.objects.filter(name__icontains=q).values("id", "name", "mobile")[:10]
    return JsonResponse({"vendors": list(vendors)})


def form_context(vendors):
    return {
        "vendors": vendors,
        "expense_head_choices": EXPENSE_HEAD_CHOICES,
        "area_choices": AREA_CHOICES,
        "payment_mode_choices": PAYMENT_MODE_CHOICES,
        "paid_by_choices": PAID_BY_CHOICES,
        "paid_from_choices": PAID_FROM_CHOICES,
        "approval_status_choices": APPROVAL_STATUS_CHOICES,
        "approved_by_choices": APPROVED_BY_CHOICES,
        "work_status_choices": WORK_STATUS_CHOICES,
        "material_received_choices": YES_NO_PARTIAL_CHOICES,
        "invoice_type_choices": INVOICE_TYPE_CHOICES,
        "today": date.today().strftime("%Y-%m-%d"),
    }


@login_required
def partner_deposits(request):
    from ..models import Partner
    partners = ['Pratap', 'Lumbaram', 'Poonaram']
    partner_labels = {
        'Pratap': 'Dr. Pratap',
        'Lumbaram': 'Mr. Lumbaram',
        'Poonaram': 'Mr. Poonaram',
    }

    if request.method == 'POST':
        partner_name = request.POST.get('partner')
        amount = request.POST.get('amount')
        date = request.POST.get('date')
        note = request.POST.get('note', '')
        if partner_name and amount and date:
            partner_obj, _ = Partner.objects.get_or_create(name=partner_name)
            PartnerDeposit.objects.create(
                partner=partner_obj,
                amount=amount,
                date=date,
                note=note,
                created_by=request.user,
            )
            messages.success(request, f"Deposit of ₹{amount} added for {partner_labels.get(partner_name, partner_name)}.")
        return redirect('hms:partner_deposits')

    deposit_sums = dict(
        PartnerDeposit.objects.values_list('partner__name')
        .annotate(total=Sum('amount'))
    )
    expense_sums = dict(
        ConstructionExpense.objects.values_list('paid_by')
        .annotate(total=Sum('total_amount'))
    )

    all_deposits = list(PartnerDeposit.objects.select_related('partner').order_by('-date'))
    all_expenses = list(ConstructionExpense.objects.order_by('-date'))

    summary = []
    for p in partners:
        total_deposited = deposit_sums.get(p) or Decimal('0')
        total_spent = expense_sums.get(p) or Decimal('0')
        summary.append({
            'key': p,
            'label': partner_labels[p],
            'deposited': total_deposited,
            'spent': total_spent,
            'balance': total_deposited - total_spent,
            'deposits': [d for d in all_deposits if d.partner.name == p],
            'expenses': [e for e in all_expenses if e.paid_by == p],
        })

    return render(request, 'hms/construction/partner_deposits.html', {
        'summary': summary,
    })


@login_required
def partner_deposit_edit(request, pk):
    from ..models import PartnerDeposit
    deposit = get_object_or_404(PartnerDeposit, pk=pk)
    if request.method == 'POST':
        deposit.amount = request.POST.get('amount')
        deposit.date = request.POST.get('date')
        deposit.note = request.POST.get('note', '')
        deposit.save()
        messages.success(request, f"Deposit updated successfully.")
        return redirect('hms:partner_deposits')
    return redirect('hms:partner_deposits')


@login_required
def partner_deposit_delete(request, pk):
    from ..models import PartnerDeposit
    deposit = get_object_or_404(PartnerDeposit, pk=pk)
    if request.method == 'POST':
        deposit.delete()
        messages.success(request, "Deposit deleted.")
    return redirect('hms:partner_deposits')

