from django.db import models
from django.contrib.auth.models import User
from .core import Patient, Department, Doctor

# ===================== BILLING =====================
class BillItem(models.Model):
    name     = models.CharField(max_length=200)
    category = models.CharField(max_length=100)
    price    = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.name} - Rs.{self.price}"


class PatientService(models.Model):
    patient  = models.ForeignKey(Patient, on_delete=models.CASCADE)
    item     = models.ForeignKey(BillItem, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)
    price    = models.DecimalField(max_digits=10, decimal_places=2)
    total    = models.DecimalField(max_digits=10, decimal_places=2)
    date     = models.DateTimeField(auto_now_add=True)


class DischargeBill(models.Model):

    PAYMENT_MODES = [
        ("CASH",   "Cash"),
        ("UPI",    "UPI"),
        ("CARD",   "Card"),
        ("CHEQUE", "Cheque"),
        ("FREE",   "Free of Cost"),
    ]

    patient      = models.OneToOneField(Patient, on_delete=models.CASCADE)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    discount     = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    advance_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    final_amount = models.DecimalField(max_digits=10, decimal_places=2)
    is_paid      = models.BooleanField(default=False)
    payment_mode = models.CharField(max_length=20, choices=PAYMENT_MODES, blank=True, null=True)
    paid_at      = models.DateTimeField(blank=True, null=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Discharge Bill - {self.patient.full_name}"


class DischargeBillItem(models.Model):
    bill     = models.ForeignKey(
        DischargeBill, on_delete=models.CASCADE,
        related_name="items", null=True, blank=True
    )
    item     = models.ForeignKey(BillItem, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)
    price    = models.DecimalField(max_digits=10, decimal_places=2)
    total    = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.bill.patient.full_name} - {self.item.name}"


class IPDAdvance(models.Model):

    PAYMENT_MODES = [
        ("CASH",   "Cash"),
        ("UPI",    "UPI"),
        ("CARD",   "Card"),
        ("CHEQUE", "Cheque"),
        ("FREE",   "Free of Cost"),
    ]

    patient      = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='advances')
    amount       = models.DecimalField(max_digits=10, decimal_places=2)
    payment_mode = models.CharField(max_length=20, choices=PAYMENT_MODES, default='CASH')
    note         = models.CharField(max_length=200, blank=True, default='')
    date         = models.DateTimeField(auto_now_add=True)

    def receipt_no(self):
        return f"ADV-{self.pk:05d}"

    def __str__(self):
        return f"{self.patient.full_name} - ₹{self.amount}"


# ===================== PROCEDURE CHARGES =====================
class ProcedureItem(models.Model):
    name      = models.CharField(max_length=200)
    price     = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} - Rs.{self.price}"


class ProcedureBill(models.Model):

    PAYMENT_MODES = (
        ("CASH", "Cash"),
        ("UPI",  "UPI"),
        ("FREE", "Free of Cost"),
    )

    patient      = models.ForeignKey(Patient,     on_delete=models.CASCADE, related_name="procedure_bills")
    department   = models.ForeignKey(Department,  on_delete=models.SET_NULL, null=True, blank=True)
    consultant   = models.ForeignKey(Doctor,      on_delete=models.SET_NULL, null=True, blank=True)
    payment_mode = models.CharField(max_length=10, choices=PAYMENT_MODES, default="CASH")
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount     = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_amount   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at   = models.DateTimeField(auto_now_add=True)
    created_by   = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def calculate_totals(self):
        total = sum(item.price for item in self.items.all())
        self.total_amount = total
        self.net_amount   = total - self.discount
        self.save()

    def __str__(self):
        return f"PB-{self.id} | {self.patient.full_name} | Rs.{self.net_amount}"


class ProcedureBillItem(models.Model):
    bill      = models.ForeignKey(ProcedureBill, on_delete=models.CASCADE, related_name="items")
    procedure = models.ForeignKey(ProcedureItem, on_delete=models.PROTECT)
    price     = models.DecimalField(max_digits=10, decimal_places=2)

    def save(self, *args, **kwargs):
        if not self.price:
            self.price = self.procedure.price
        super().save(*args, **kwargs)
        self.bill.calculate_totals()

    def __str__(self):
        return f"{self.procedure.name} - Rs.{self.price}"


