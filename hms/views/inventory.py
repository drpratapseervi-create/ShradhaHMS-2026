from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import F
from django.urls import reverse

from ..models import DrugMaster, InventoryItem, StockIn, StockOut, Supplier
from ..pharmacy.stock import InsufficientStock, issue_stock, receive_stock


@login_required
def inventory_dashboard(request):
    total_items = InventoryItem.objects.count()
    low_stock   = InventoryItem.objects.filter(current_stock__lte=F('minimum_stock'))  # ← F not models.F
    recent_in   = StockIn.objects.select_related('item').order_by('-created_at')[:5]
    recent_out  = StockOut.objects.select_related('item').order_by('-created_at')[:5]
    return render(request, "inventory/dashboard.html", {
        "total_items": total_items,
        "low_stock": low_stock,
        "recent_in": recent_in,
        "recent_out": recent_out,
    })


@login_required
def inventory_report(request):
    items     = InventoryItem.objects.all().order_by("category", "name")
    low_stock = items.filter(current_stock__lte=F('minimum_stock'))  # ← F not models.F
    return render(request, "inventory/report.html", {
        "items": items,
        "low_stock": low_stock,
    })


@login_required
def inventory_items(request):
    category = request.GET.get("category", "")
    search   = request.GET.get("q", "")
    items    = InventoryItem.objects.select_related("supplier").order_by("name")
    if category:
        items = items.filter(category=category)
    if search:
        items = items.filter(name__icontains=search)
    return render(request, "inventory/items.html", {"items": items, "category": category, "search": search})


@login_required
def inventory_item_new(request):
    suppliers = Supplier.objects.all().order_by("name")
    if request.method == "POST":
        item = InventoryItem.objects.create(
            name          = request.POST.get("name"),
            category      = request.POST.get("category"),
            unit          = request.POST.get("unit"),
            minimum_stock = request.POST.get("minimum_stock", 10),
            supplier_id   = request.POST.get("supplier") or None,
            drug_id       = request.POST.get("drug") or None,
            pack_size     = request.POST.get("pack_size") or 1,
            gst_percent   = request.POST.get("gst_percent") or 12,
            hsn_code      = request.POST.get("hsn_code", "").strip(),
            schedule      = request.POST.get("schedule") or "OTC",
        )
        # Stock (with batch, expiry and MRP) is added through Stock In.
        return redirect(f"{reverse('hms:stock_in_create')}?item={item.id}")
    return render(request, "inventory/item_form.html", {
        "suppliers": suppliers,
        "drugs": DrugMaster.objects.filter(is_active=True).order_by("name"),
        "schedules": InventoryItem.SCHEDULE_CHOICES,
    })


@login_required
def inventory_item_detail(request, id):
    item     = get_object_or_404(InventoryItem, id=id)
    stock_ins  = item.stock_ins.order_by("-date")[:20]
    stock_outs = item.stock_outs.order_by("-date")[:20]
    return render(request, "inventory/item_detail.html", {
        "item": item,
        "stock_ins": stock_ins,
        "stock_outs": stock_outs,
        "batches": item.batches.filter(quantity_remaining__gt=0),
    })


def _decimal(value):
    try:
        return Decimal(value or "0")
    except InvalidOperation:
        return Decimal("0")


@login_required
def stock_in_create(request):
    items     = InventoryItem.objects.all().order_by("name")
    suppliers = Supplier.objects.all().order_by("name")
    if request.method == "POST":
        item = get_object_or_404(InventoryItem, id=request.POST.get("item"))
        pack = item.pack_size or 1
        # Received in packs (strips/bottles) + loose units; stored per unit.
        units = int(request.POST.get("packs") or 0) * pack + int(request.POST.get("loose_units") or 0)
        if units <= 0:
            messages.error(request, "Enter the quantity received.")
            return redirect(f"{reverse('hms:stock_in_create')}?item={item.id}")
        receive_stock(
            item           = item,
            supplier       = Supplier.objects.filter(id=request.POST.get("supplier") or 0).first(),
            quantity       = units,
            batch_no       = request.POST.get("batch_no", "").strip(),
            expiry_date    = request.POST.get("expiry_date") or None,
            purchase_price = (_decimal(request.POST.get("purchase_price_pack")) / pack).quantize(Decimal("0.01")),
            mrp            = (_decimal(request.POST.get("mrp_pack")) / pack).quantize(Decimal("0.01")),
            date           = request.POST.get("date") or None,
            notes          = request.POST.get("notes", ""),
            user           = request.user,
        )
        messages.success(request, f"Received {units} {item.unit.lower()}(s) of {item.name}.")
        return redirect("hms:inventory_dashboard")
    return render(request, "inventory/stock_in_form.html", {"items": items, "suppliers": suppliers})


@login_required
def stock_out_create(request):
    items = InventoryItem.objects.filter(current_stock__gt=0).order_by("name")
    if request.method == "POST":
        item = get_object_or_404(InventoryItem, id=request.POST.get("item"))
        try:
            issue_stock(
                item             = item,
                quantity         = int(request.POST.get("quantity") or 0),
                issued_to        = request.POST.get("issued_to"),
                issued_to_detail = request.POST.get("issued_to_detail", ""),
                notes            = request.POST.get("notes", ""),
                date             = request.POST.get("date") or None,
                user             = request.user,
            )
        except (InsufficientStock, ValueError) as e:
            messages.error(request, f"Not issued: {e}")
            return redirect("hms:stock_out_create")
        return redirect("hms:inventory_dashboard")
    return render(request, "inventory/stock_out_form.html", {"items": items})


@login_required
def supplier_list(request):
    suppliers = Supplier.objects.all().order_by("name")
    return render(request, "inventory/suppliers.html", {"suppliers": suppliers})


@login_required
def supplier_new(request):
    if request.method == "POST":
        Supplier.objects.create(
            name    = request.POST.get("name"),
            contact = request.POST.get("contact"),
            email   = request.POST.get("email"),
            address = request.POST.get("address"),
        )
        return redirect("hms:supplier_list")
    return render(request, "inventory/supplier_form.html")

