from django.db import models
from django.contrib.auth.models import User
from datetime import date

# ===================== INVENTORY =====================
class Supplier(models.Model):
    name       = models.CharField(max_length=200)
    contact    = models.CharField(max_length=20, blank=True)
    email      = models.EmailField(blank=True)
    address    = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class InventoryItem(models.Model):
    CATEGORY_CHOICES = [
        ("Medicine",  "Medicine"),
        ("Surgical",  "Surgical Supply"),
        ("Equipment", "Equipment"),
        ("Other",     "Other"),
    ]
    UNIT_CHOICES = [
        ("Tablet",  "Tablet"), ("Capsule", "Capsule"),
        ("Vial",    "Vial"),   ("Ampoule", "Ampoule"),
        ("Bottle",  "Bottle"), ("Strip",   "Strip"),
        ("Piece",   "Piece"),  ("Box",     "Box"),
        ("Kg",      "Kg"),     ("Litre",   "Litre"),
    ]

    SCHEDULE_CHOICES = [
        ("OTC", "OTC / Non-scheduled"),
        ("H",   "Schedule H"),
        ("H1",  "Schedule H1"),
        ("X",   "Schedule X"),
    ]
    # Units counted and sold loose (a strip's tablets can be sold individually).
    LOOSE_UNITS = ("Tablet", "Capsule")

    name          = models.CharField(max_length=200)
    category      = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="Medicine")
    unit          = models.CharField(max_length=20, choices=UNIT_CHOICES, default="Tablet")
    current_stock = models.IntegerField(default=0)  # in units; kept equal to the sum of batch quantities
    minimum_stock = models.IntegerField(default=10)
    supplier      = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    # ── Pharmacy ──
    drug        = models.ForeignKey("DrugMaster", on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="inventory_items",
                                    help_text="Drug Master entry doctors prescribe this as")
    pack_size   = models.PositiveIntegerField(default=1, help_text="Units per strip/pack, e.g. 10 tablets")
    gst_percent = models.DecimalField(max_digits=5, decimal_places=2, default=12)
    hsn_code    = models.CharField(max_length=10, blank=True)
    schedule    = models.CharField(max_length=3, choices=SCHEDULE_CHOICES, default="OTC")

    def __str__(self):
        return f"{self.name} ({self.unit})"

    @property
    def sells_loose(self):
        return self.unit in self.LOOSE_UNITS

    @property
    def is_low_stock(self):
        return self.current_stock <= self.minimum_stock


class StockIn(models.Model):
    item           = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name="stock_ins")
    supplier       = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True)
    quantity       = models.IntegerField()  # units
    batch_no       = models.CharField(max_length=50, blank=True)
    expiry_date    = models.DateField(null=True, blank=True)
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # per unit
    mrp            = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # per unit, GST-inclusive
    date           = models.DateField(default=date.today)
    notes          = models.TextField(blank=True)
    created_by     = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        is_new = not self.pk
        if is_new:
            self.item.current_stock += int(self.quantity)
            self.item.save()
        super().save(*args, **kwargs)
        if is_new:
            # Every receipt is its own batch, so stock can be issued first-expiry-first-out.
            StockBatch.objects.create(
                item=self.item, stock_in=self, batch_no=self.batch_no,
                expiry_date=self.expiry_date, quantity_remaining=int(self.quantity),
                purchase_price=self.purchase_price, mrp=self.mrp,
            )

    def __str__(self):
        return f"IN: {self.item.name} x{self.quantity}"


class StockBatch(models.Model):
    """Stock remaining from one StockIn. InventoryItem.current_stock is the sum of these."""
    item               = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name="batches")
    stock_in           = models.OneToOneField(StockIn, on_delete=models.CASCADE, related_name="batch")
    batch_no           = models.CharField(max_length=50, blank=True)
    expiry_date        = models.DateField(null=True, blank=True)
    quantity_remaining = models.IntegerField(default=0)
    purchase_price     = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # per unit
    mrp                = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # per unit

    class Meta:
        ordering = ["expiry_date", "id"]

    def __str__(self):
        return f"{self.item.name} | {self.batch_no or '—'} | exp {self.expiry_date or '—'} | {self.quantity_remaining}"

    @property
    def is_expired(self):
        return bool(self.expiry_date and self.expiry_date < date.today())


class StockOut(models.Model):
    ISSUED_TO_CHOICES = [
        ("Ward",     "Ward"),
        ("OT",       "Operation Theatre"),
        ("Pharmacy", "Pharmacy"),
        ("Patient",  "Patient"),
        ("Other",    "Other"),
    ]

    item             = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name="stock_outs")
    batch            = models.ForeignKey(StockBatch, on_delete=models.PROTECT, null=True, blank=True,
                                         related_name="stock_outs")
    quantity         = models.IntegerField()
    issued_to        = models.CharField(max_length=20, choices=ISSUED_TO_CHOICES, default="Ward")
    issued_to_detail = models.CharField(max_length=100, blank=True)
    date             = models.DateField(default=date.today)
    notes            = models.TextField(blank=True)
    created_by       = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Use hms.pharmacy.stock.issue_stock() rather than creating these directly:
        # it picks batches first-expiry-first-out and refuses to overdraw.
        if not self.pk:
            self.item.current_stock -= int(self.quantity)
            self.item.save()
            if self.batch_id:
                self.batch.quantity_remaining -= int(self.quantity)
                self.batch.save(update_fields=["quantity_remaining"])
        super().save(*args, **kwargs)

    def __str__(self):
        return f"OUT: {self.item.name} x{self.quantity}"


