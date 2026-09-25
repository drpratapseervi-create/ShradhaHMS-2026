from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models

from .core import Patient, Doctor
from .opd import Consultation, Prescription
from .inventory import InventoryItem, StockBatch, StockOut
from .ipd import IPDAdmission


# ===================== PHARMACY DISPENSING =====================
class PharmacyBill(models.Model):
    """
    One sale at the pharmacy counter: against an OPD prescription, or a walk-in
    (patient optional; name/mobile kept on the bill). Prices are MRP, GST-inclusive.
    """
    PAYMENT_MODES = [
        ("CASH", "Cash"),
        ("UPI",  "UPI"),
        ("FREE", "Free of Cost"),
        ("IPD",  "Charged to IPD bill"),  # inpatient issue: settled on the discharge bill, not at the counter
    ]
    STATUS_CHOICES = [
        ("PAID",      "Paid"),
        ("CANCELLED", "Cancelled"),
    ]

    bill_no       = models.CharField(max_length=20, unique=True, blank=True)
    patient       = models.ForeignKey(Patient, on_delete=models.PROTECT, null=True, blank=True,
                                      related_name="pharmacy_bills")
    consultation  = models.ForeignKey(Consultation, on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name="pharmacy_bills")
    admission     = models.ForeignKey(IPDAdmission, on_delete=models.PROTECT, null=True, blank=True,
                                      related_name="pharmacy_bills")
    prescribed_snapshot = models.JSONField(default=list, blank=True,
                                           help_text="Medicines on the consultation's prescription when this bill was made")
    customer_name = models.CharField(max_length=150, blank=True)
    customer_mobile = models.CharField(max_length=20, blank=True)
    doctor        = models.ForeignKey(Doctor, on_delete=models.SET_NULL, null=True, blank=True)
    doctor_name   = models.CharField(max_length=150, blank=True, help_text="Prescriber, if not one of our doctors")

    gross_amount  = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount      = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_amount    = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    returned_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                          help_text="Total refunded/credited through partial returns")
    payment_mode  = models.CharField(max_length=10, choices=PAYMENT_MODES, default="CASH")
    status        = models.CharField(max_length=10, choices=STATUS_CHOICES, default="PAID")

    created_by    = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name="pharmacy_bills")
    created_at    = models.DateTimeField(auto_now_add=True)
    cancelled_by  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name="+")
    cancelled_at  = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.bill_no} | {self.display_name} | Rs.{self.net_amount}"

    @property
    def display_name(self):
        return self.patient.full_name if self.patient else (self.customer_name or "Walk-in")

    @property
    def prescriber(self):
        return self.doctor.full_name if self.doctor else self.doctor_name

    @property
    def amount_after_returns(self):
        return self.net_amount - self.returned_amount

    @property
    def is_ipd(self):
        return self.payment_mode == "IPD"

    @property
    def discount_factor(self):
        """Share of MRP actually charged (net / gross); used to value returns."""
        return (self.net_amount / self.gross_amount) if self.gross_amount else Decimal("0")

    def gst_summary(self):
        """[(rate, taxable, cgst, sgst)] per GST rate, back-calculated from GST-inclusive MRP."""
        by_rate = {}
        for it in self.items.all():
            by_rate.setdefault(it.gst_percent, Decimal("0"))
            by_rate[it.gst_percent] += it.amount
        # Spread the bill discount proportionally so GST is on the value actually charged.
        factor = self.discount_factor
        rows = []
        for rate, amount in sorted(by_rate.items()):
            charged = amount * factor
            taxable = (charged / (1 + rate / 100)).quantize(Decimal("0.01"))
            gst = charged.quantize(Decimal("0.01")) - taxable
            half = (gst / 2).quantize(Decimal("0.01"))
            rows.append((rate, taxable, half, gst - half))
        return rows


class PharmacyBillItem(models.Model):
    """One batch's worth of one medicine on a bill (a line spanning two batches is two rows)."""
    bill         = models.ForeignKey(PharmacyBill, on_delete=models.CASCADE, related_name="items")
    item         = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="pharmacy_sales")
    batch        = models.ForeignKey(StockBatch, on_delete=models.PROTECT, related_name="pharmacy_sales")
    stock_out    = models.OneToOneField(StockOut, on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name="pharmacy_bill_item")
    prescription = models.ForeignKey(Prescription, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="dispensed_items")
    # The consultation screen deletes and recreates Prescription rows on every save, which
    # nulls the FK above; this snapshot is what "already dispensed" is matched on.
    prescribed_as = models.CharField(max_length=200, blank=True,
                                     help_text="Prescribed medicine name at dispensing time")
    quantity     = models.PositiveIntegerField()
    returned_quantity = models.PositiveIntegerField(default=0)
    mrp          = models.DecimalField(max_digits=10, decimal_places=2)  # per unit
    gst_percent  = models.DecimalField(max_digits=5, decimal_places=2)
    amount       = models.DecimalField(max_digits=10, decimal_places=2)  # quantity * mrp

    def __str__(self):
        return f"{self.item.name} x{self.quantity}"

    @property
    def returnable_quantity(self):
        return self.quantity - self.returned_quantity


class PharmacyReturn(models.Model):
    """A partial return against one bill: its own numbered credit note."""
    return_no     = models.CharField(max_length=20, unique=True)
    bill          = models.ForeignKey(PharmacyBill, on_delete=models.PROTECT, related_name="returns")
    reason        = models.CharField(max_length=200, blank=True)
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_by    = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.return_no} (bill {self.bill.bill_no}) Rs.{self.refund_amount}"


class PharmacyReturnItem(models.Model):
    pharmacy_return = models.ForeignKey(PharmacyReturn, on_delete=models.CASCADE, related_name="items")
    bill_item       = models.ForeignKey(PharmacyBillItem, on_delete=models.PROTECT, related_name="return_items")
    quantity        = models.PositiveIntegerField()
    amount          = models.DecimalField(max_digits=10, decimal_places=2)  # refund value after bill discount

    def __str__(self):
        return f"{self.bill_item.item.name} x{self.quantity} returned"
