from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import F

from ..models import InventoryItem, StockIn, StockOut, Supplier


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
        InventoryItem.objects.create(
            name          = request.POST.get("name"),
            category      = request.POST.get("category"),
            unit          = request.POST.get("unit"),
            current_stock = request.POST.get("current_stock", 0),
            minimum_stock = request.POST.get("minimum_stock", 10),
            supplier_id   = request.POST.get("supplier") or None,
        )
        return redirect("hms:inventory_items")
    return render(request, "inventory/item_form.html", {"suppliers": suppliers})


@login_required
def inventory_item_detail(request, id):
    item     = get_object_or_404(InventoryItem, id=id)
    stock_ins  = item.stock_ins.order_by("-date")[:20]
    stock_outs = item.stock_outs.order_by("-date")[:20]
    return render(request, "inventory/item_detail.html", {
        "item": item,
        "stock_ins": stock_ins,
        "stock_outs": stock_outs,
    })


@login_required
def stock_in_create(request):
    items     = InventoryItem.objects.all().order_by("name")
    suppliers = Supplier.objects.all().order_by("name")
    if request.method == "POST":
        StockIn.objects.create(
            item_id        = request.POST.get("item"),
            supplier_id    = request.POST.get("supplier") or None,
            quantity       = request.POST.get("quantity"),
            batch_no       = request.POST.get("batch_no"),
            expiry_date    = request.POST.get("expiry_date") or None,
            purchase_price = request.POST.get("purchase_price", 0),
            date           = request.POST.get("date"),
            notes          = request.POST.get("notes"),
            created_by     = request.user,
        )
        return redirect("hms:inventory_dashboard")
    return render(request, "inventory/stock_in_form.html", {"items": items, "suppliers": suppliers})


@login_required
def stock_out_create(request):
    items = InventoryItem.objects.filter(current_stock__gt=0).order_by("name")
    if request.method == "POST":
        StockOut.objects.create(
            item_id          = request.POST.get("item"),
            quantity         = request.POST.get("quantity"),
            issued_to        = request.POST.get("issued_to"),
            issued_to_detail = request.POST.get("issued_to_detail"),
            date             = request.POST.get("date"),
            notes            = request.POST.get("notes"),
            created_by       = request.user,
        )
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

