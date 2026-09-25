"""
Batch-level stock movements. All stock leaving inventory should go through
issue_stock() so batches are consumed first-expiry-first-out, expired batches
are never issued, and stock can't go negative.
"""

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from hms.models import InventoryItem, StockBatch, StockIn, StockOut


class InsufficientStock(Exception):
    def __init__(self, item, requested, available):
        self.item, self.requested, self.available = item, requested, available
        super().__init__(f"{item.name}: {requested} requested, only {available} in stock")


def sellable_batches(item):
    """Non-expired batches with stock, earliest expiry first (no-expiry batches last)."""
    return (
        StockBatch.objects.filter(item=item, quantity_remaining__gt=0)
        .exclude(expiry_date__lt=timezone.localdate())
        .order_by(F("expiry_date").asc(nulls_last=True), "id")
    )


def sellable_quantity(item):
    return sum(b.quantity_remaining for b in sellable_batches(item))


@transaction.atomic
def receive_stock(*, item, quantity, batch_no="", expiry_date=None, purchase_price=0, mrp=0,
                  supplier=None, user=None, date=None, notes=""):
    """Record a receipt (creates the StockIn and its StockBatch)."""
    return StockIn.objects.create(
        item=item, supplier=supplier, quantity=int(quantity), batch_no=batch_no,
        expiry_date=expiry_date, purchase_price=purchase_price, mrp=mrp,
        date=date or timezone.localdate(), notes=notes, created_by=user,
    )


@transaction.atomic
def issue_stock(*, item, quantity, issued_to, issued_to_detail="", user=None, batch=None, notes="", date=None):
    """
    Take `quantity` units out, from `batch` if given, else across batches FEFO.
    Returns the StockOut rows created (one per batch touched).
    Raises InsufficientStock without changing anything if there isn't enough.
    """
    quantity = int(quantity)
    if quantity <= 0:
        raise ValueError("Quantity must be positive")
    item = InventoryItem.objects.select_for_update().get(pk=item.pk)

    if batch is not None:
        batches = list(sellable_batches(item).select_for_update().filter(pk=batch.pk))
    else:
        batches = list(sellable_batches(item).select_for_update())
    available = sum(b.quantity_remaining for b in batches)
    if available < quantity:
        raise InsufficientStock(item, quantity, available)

    outs, remaining = [], quantity
    for b in batches:
        if remaining == 0:
            break
        take = min(remaining, b.quantity_remaining)
        b.item = item  # share the locked instance so current_stock updates accumulate
        outs.append(StockOut.objects.create(
            item=item, batch=b, quantity=take, issued_to=issued_to,
            issued_to_detail=issued_to_detail[:100], notes=notes, created_by=user,
            date=date or timezone.localdate(),
        ))
        remaining -= take
    return outs


@transaction.atomic
def reverse_issue(stock_out):
    """Put a StockOut's units back into its batch and delete it (used when a bill is cancelled)."""
    item = InventoryItem.objects.select_for_update().get(pk=stock_out.item_id)
    item.current_stock += stock_out.quantity
    item.save(update_fields=["current_stock"])
    if stock_out.batch_id:
        StockBatch.objects.filter(pk=stock_out.batch_id).update(
            quantity_remaining=F("quantity_remaining") + stock_out.quantity
        )
    stock_out.delete()
