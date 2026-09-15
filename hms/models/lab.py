from django.db import models

class InvestigationCategory(models.Model):

    DEPT_CHOICES = [
        ("RADIOLOGY",      "Radiology"),
        ("HISTOPATHOLOGY", "Histopathology"),
        ("BIOCHEMISTRY",   "Biochemistry"),
        ("HEMATOLOGY",     "Hematology"),
        ("MICROBIOLOGY",   "Microbiology"),
        ("CARDIOLOGY",     "Cardiology"),
        ("ECG",            "ECG"),
        ("ENDOSCOPY",      "Endoscopy & Procedures"),
        ("OTHER",          "Other"),
    ]

    name      = models.CharField(max_length=100)
    dept_code = models.CharField(
        max_length=20,
        choices=DEPT_CHOICES,
        default="OTHER",
        help_text="Used in reports for department-wise billing summary."
    )

    class Meta:
        verbose_name        = "Investigation Category"
        verbose_name_plural = "Investigation Categories"
        ordering            = ["dept_code", "name"]

    def __str__(self):
        return f"{self.name} [{self.get_dept_code_display()}]"


# =====================================================================
# INVESTIGATION
# =====================================================================
class Investigation(models.Model):
    category  = models.ForeignKey(InvestigationCategory, on_delete=models.CASCADE)
    name      = models.CharField(max_length=255)
    price     = models.DecimalField(max_digits=8, decimal_places=2)
    is_active = models.BooleanField(default=True)
    loinc_panel_code = models.CharField(
        max_length=20, blank=True, null=True,
        help_text="LOINC panel code e.g. '58410-2' for CBC"
    )
    sort_order = models.IntegerField(default=9999, blank=True)

    class Meta:
        ordering = ["sort_order", "category__dept_code", "name"]

    def __str__(self):
        return f"{self.name} ({self.category.name})"


# =====================================================================
# INVESTIGATION BILL
# =====================================================================
class InvestigationBill(models.Model):

    PAYMENT_MODES = [
        ("CASH", "Cash"),
        ("UPI",  "UPI"),
    ]

    patient      = models.ForeignKey("Patient",      on_delete=models.CASCADE)
    consultation = models.ForeignKey("Consultation", on_delete=models.SET_NULL,
                                     null=True, blank=True)
    admission    = models.ForeignKey("IPDAdmission", on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name="investigation_bills")
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    discount     = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_amount   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paid         = models.BooleanField(default=True)
    payment_mode = models.CharField(max_length=10, choices=PAYMENT_MODES, default="CASH")
    created_at   = models.DateTimeField(auto_now_add=True)
    created_by   = models.ForeignKey("auth.User", on_delete=models.SET_NULL,
                                     null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Lab Bill #{self.id} - {self.patient.full_name}"


class InvestigationBillItem(models.Model):

    ADDED_BY_CHOICES = [
        ("DOCTOR",    "Doctor"),
        ("RECEPTION", "Reception"),
    ]

    bill          = models.ForeignKey(InvestigationBill, on_delete=models.CASCADE,
                                      related_name="items")
    investigation = models.ForeignKey(Investigation, on_delete=models.CASCADE)
    price         = models.DecimalField(max_digits=8, decimal_places=2)
    added_by      = models.CharField(max_length=20, choices=ADDED_BY_CHOICES)

    def __str__(self):
        return f"{self.investigation.name} - ₹{self.price}"

class InvestigationParameter(models.Model):
    investigation = models.ForeignKey(
        "Investigation", on_delete=models.CASCADE, related_name="parameters"
    )
    name = models.CharField(max_length=120)
    unit = models.CharField(max_length=30, blank=True)

    min_value    = models.FloatField(null=True, blank=True)
    max_value    = models.FloatField(null=True, blank=True)
    male_range   = models.CharField(max_length=50, blank=True)
    female_range = models.CharField(max_length=50, blank=True)
    critical_low  = models.FloatField(null=True, blank=True)
    critical_high = models.FloatField(null=True, blank=True)
    loinc_code = models.CharField(
        max_length=20, blank=True, null=True,
        help_text="LOINC code e.g. '718-7' for Haemoglobin"
    )
    loinc_display = models.CharField(
        max_length=100, blank=True, null=True,
        help_text="LOINC display name e.g. 'Hemoglobin [Mass/volume] in Blood'"
    )

    RESULT_TYPES = (
        ("numeric",  "Numeric"),
        ("pos_neg",  "Positive / Negative"),
        ("reactive", "Reactive / Non-Reactive"),
        ("text",     "Text"),
    )
    result_type    = models.CharField(max_length=20, choices=RESULT_TYPES, default="numeric")
    group          = models.CharField(max_length=50, blank=True)
    method         = models.CharField(max_length=100, blank=True)
    method_description = models.TextField(
        blank=True,
        help_text="Full descriptive method sentence for the printed report, "
                   "e.g. 'Hexokinase / Enzymatic method using glucose-6-phosphate "
                   "dehydrogenase coupled reaction.' Falls back to 'method' if blank."
    )
    order          = models.IntegerField(default=1)
    show_in_report = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.investigation} - {self.name}"

    class Meta:
        ordering = ["investigation", "order"]


# ===================== INVESTIGATION RESULT =====================
class InvestigationResult(models.Model):
    bill_item = models.ForeignKey(
        InvestigationBillItem, on_delete=models.CASCADE, related_name="results"
    )
    parameter  = models.ForeignKey(InvestigationParameter, on_delete=models.CASCADE)
    value      = models.CharField(max_length=100, help_text="Result value entered by lab technician")
    entered_at = models.DateTimeField(auto_now=True)
    entered_by = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering       = ["parameter__order"]
        unique_together = ["bill_item", "parameter"]

    def __str__(self):
        return f"{self.parameter.name}: {self.value}"

