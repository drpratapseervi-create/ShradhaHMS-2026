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

    name          = models.CharField(max_length=200)
    category      = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="Medicine")
    unit          = models.CharField(max_length=20, choices=UNIT_CHOICES, default="Tablet")
    current_stock = models.IntegerField(default=0)
    minimum_stock = models.IntegerField(default=10)
    supplier      = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.unit})"

    @property
    def is_low_stock(self):
        return self.current_stock <= self.minimum_stock


class StockIn(models.Model):
    item           = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name="stock_ins")
    supplier       = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True)
    quantity       = models.IntegerField()
    batch_no       = models.CharField(max_length=50, blank=True)
    expiry_date    = models.DateField(null=True, blank=True)
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    date           = models.DateField(default=date.today)
    notes          = models.TextField(blank=True)
    created_by     = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.pk:
            self.item.current_stock += int(self.quantity)
            self.item.save()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"IN: {self.item.name} x{self.quantity}"


class StockOut(models.Model):
    ISSUED_TO_CHOICES = [
        ("Ward",     "Ward"),
        ("OT",       "Operation Theatre"),
        ("Pharmacy", "Pharmacy"),
        ("Patient",  "Patient"),
        ("Other",    "Other"),
    ]

    item             = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name="stock_outs")
    quantity         = models.IntegerField()
    issued_to        = models.CharField(max_length=20, choices=ISSUED_TO_CHOICES, default="Ward")
    issued_to_detail = models.CharField(max_length=100, blank=True)
    date             = models.DateField(default=date.today)
    notes            = models.TextField(blank=True)
    created_by       = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.pk:
            self.item.current_stock -= int(self.quantity)
            self.item.save()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"OUT: {self.item.name} x{self.quantity}"


