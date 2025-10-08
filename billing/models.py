# C:\ShradhaHMS_Full\ShradhaHMS_Full\billing\models.py
from django.db import models
from django.utils import timezone
from decimal import Decimal

# =========================
#   IPD Admission (Core)
# =========================
class Admission(models.Model):
    """IPD Admission record kept simple (no cross-app FK to avoid coupling)."""
    patient_name = models.CharField(max_length=200)
    mrn = models.CharField("Hospital No / IPD No", max_length=50, blank=True)
    reg_no = models.CharField(max_length=50, blank=True)

    ward = models.CharField(max_length=100, blank=True)
    bed = models.CharField(max_length=50, blank=True)
    category = models.CharField(
        max_length=100,
        blank=True,
        help_text="GENERAL / DELUXE / PRIVATE etc."
    )
    doctor = models.CharField(max_length=200, blank=True)

    admit_at = models.DateTimeField(default=timezone.now)
    discharge_at = models.DateTimeField(null=True, blank=True)

    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"IPD #{self.id} - {self.patient_name} ({self.ward}/{self.bed})"


# =========================
#        Charge Item
# =========================
class ChargeItem(models.Model):
    TYPE_CHOICES = [
        ("PROC", "Procedure / OT / Surgeon"),
        ("INV",  "Investigation / Lab / USG / X-Ray"),
        ("BED",  "Bed Charges / Room Rent"),
        ("CONS", "Consultation"),
        ("PHARM","Pharmacy"),
        ("NURS", "Nursing / General"),
        ("COMP", "Compulsory / Registration"),
        ("ER",   "Emergency / Casualty"),
    ]

    admission = models.ForeignKey(
        Admission,
        on_delete=models.CASCADE,
        related_name="charges"
    )
    date = models.DateField(default=timezone.localdate)
    type = models.CharField(max_length=5, choices=TYPE_CHOICES)
    particulars = models.CharField(max_length=255)

    qty = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("1.00"))
    rate = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    sac_code = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["date", "id"]

    @property
    def amount(self) -> Decimal:
        q = self.qty or Decimal("0.00")
        r = self.rate or Decimal("0.00")
        return (q * r).quantize(Decimal("0.01"))

    def __str__(self) -> str:
        return f"{self.get_type_display()} - {self.particulars} (₹{self.amount})"


# =========================
#      Advance Payment
# =========================
class AdvancePayment(models.Model):
    MODE_CHOICES = [
        ("Cash", "Cash"),
        ("Card", "Card"),
        ("UPI", "UPI"),
        ("Cheque", "Cheque"),
        ("Other", "Other"),
    ]

    admission = models.ForeignKey(
        Admission,
        on_delete=models.CASCADE,
        related_name="advances"
    )
    date = models.DateField(default=timezone.localdate)
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    # Common fields used in workflows / forms
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default="Cash")
    ref_no = models.CharField("Reference / Receipt No", max_length=50, blank=True)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["date", "id"]

    def __str__(self) -> str:
        return f"Advance ₹{self.amount} ({self.mode}) for IPD #{self.admission_id}"


# =========================
#         Final Bill
# =========================
class FinalBill(models.Model):
    admission = models.OneToOneField(
        Admission,
        on_delete=models.CASCADE,
        related_name="final_bill"
    )
    bill_no = models.CharField(max_length=30, blank=True)

    # commercial fields
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    cgst = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    sgst = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    # status / meta
    is_finalized = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    remarks = models.TextField(blank=True)

    # ---- helpers (totals) ----
    def _sum_by_type(self, type_code: str) -> Decimal:
        total = Decimal("0.00")
        for c in self.admission.charges.filter(type=type_code):
            total += c.amount
        return total.quantize(Decimal("0.01"))

    @property
    def total_procedure(self) -> Decimal:     return self._sum_by_type("PROC")
    @property
    def total_investigation(self) -> Decimal: return self._sum_by_type("INV")
    @property
    def total_bed(self) -> Decimal:           return self._sum_by_type("BED")
    @property
    def total_consultation(self) -> Decimal:  return self._sum_by_type("CONS")
    @property
    def total_pharmacy(self) -> Decimal:      return self._sum_by_type("PHARM")
    @property
    def total_nursing(self) -> Decimal:       return self._sum_by_type("NURS")
    @property
    def total_compulsory(self) -> Decimal:    return self._sum_by_type("COMP")
    @property
    def total_er(self) -> Decimal:            return self._sum_by_type("ER")

    @property
    def gross(self) -> Decimal:
        total = (
            self.total_procedure + self.total_investigation + self.total_bed +
            self.total_consultation + self.total_pharmacy + self.total_nursing +
            self.total_compulsory + self.total_er
        )
        return total.quantize(Decimal("0.01"))

    @property
    def net_amount(self) -> Decimal:
        val = self.gross - (self.discount or Decimal("0.00")) + (self.cgst or 0) + (self.sgst or 0)
        return max(val, Decimal("0.00")).quantize(Decimal("0.01"))

    @property
    def advance_total(self) -> Decimal:
        total = Decimal("0.00")
        for a in self.admission.advances.all():
            total += (a.amount or Decimal("0.00"))
        return total.quantize(Decimal("0.01"))

    @property
    def net_payable(self) -> Decimal:
        val = self.net_amount - self.advance_total
        return max(val, Decimal("0.00")).quantize(Decimal("0.01"))

    def __str__(self) -> str:
        return f"Final Bill for IPD #{self.admission_id}"

