from django.db import models
from django.contrib.auth.models import User
from .core import Patient

# ======================================================
# TPA PATIENTS -- Cashless (Private/Corporate TPA & Govt Scheme)
# ======================================================

TPA_SCHEME_TYPE_CHOICES = [
    ("private", "Private/Corporate TPA (Insurance)"),
    ("government", "Government Scheme (MAA Yojana / Ayushman Bharat)"),
]

TPA_STATUS_CHOICES = [
    ("pending", "Pending"),
    ("approved", "Approved"),
    ("query_raised", "Query Raised"),
    ("settled", "Settled"),
    ("rejected", "Rejected"),
]

TPA_DOCUMENT_TYPE_CHOICES = [
    ("preauth_letter", "Pre-auth Letter"),
    ("discharge_summary", "Discharge Summary"),
    ("other", "Other"),
]


class TPAScheme(models.Model):
    """Master dropdown of TPA / insurance companies and government schemes."""
    name = models.CharField(max_length=150)
    scheme_type = models.CharField(max_length=12, choices=TPA_SCHEME_TYPE_CHOICES)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "TPA / Scheme"
        verbose_name_plural = "TPA / Schemes"
        constraints = [
            models.UniqueConstraint(fields=["name", "scheme_type"], name="unique_tpa_scheme_name_per_type"),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_scheme_type_display()})"


class TPAPatient(models.Model):
    """
    A cashless case (Private/Corporate TPA insurance OR Government scheme
    such as MAA Yojana / Ayushman Bharat) tracked against a hospital patient.

    `patient` is nullable because the daily MAA Yojana import auto-creates a
    draft row (is_draft=True) for any TID it cannot match to an existing
    record -- staff must then link it to the correct Patient/UHID by hand.
    """
    patient = models.ForeignKey(
        Patient, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="tpa_cases"
    )
    patient_name_raw = models.CharField(
        max_length=150, blank=True, default="",
        help_text="Patient name as it appeared on an import row, kept until linked to a UHID."
    )
    is_draft = models.BooleanField(
        default=False,
        help_text="Auto-created from an unmatched import row -- needs staff to link the correct UHID."
    )

    scheme_type = models.CharField(max_length=12, choices=TPA_SCHEME_TYPE_CHOICES)
    scheme = models.ForeignKey(
        TPAScheme, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="cases"
    )
    scheme_name_raw = models.CharField(
        max_length=150, blank=True, default="",
        help_text="Scheme/TPA name as imported, kept if it didn't match a known scheme."
    )

    policy_no = models.CharField(
        "Policy No. / MAA-Yojana Beneficiary ID",
        max_length=100, blank=True, default="", db_index=True
    )
    tid_number = models.CharField(
        "Pre-auth / TID Number",
        max_length=100, blank=True, default="", db_index=True
    )

    admission_date = models.DateField(null=True, blank=True)
    diagnosis = models.TextField(blank=True, default="")
    package_code = models.CharField(max_length=100, blank=True, default="")
    approved_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=TPA_STATUS_CHOICES, default="pending")

    remarks = models.TextField(blank=True, default="")

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="tpa_created")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "TPA Patient"
        verbose_name_plural = "TPA Patients"

    def __str__(self):
        who = self.patient.full_name if self.patient else (self.patient_name_raw or "Unlinked")
        return f"{who} -- {self.tid_number or self.policy_no or 'No TID'}"

    @property
    def display_name(self):
        return self.patient.full_name if self.patient else self.patient_name_raw

    @property
    def display_uhid(self):
        return self.patient.uhid if self.patient else "--"


def tpa_document_upload_path(instance, filename):
    return f"tpa_documents/{instance.tpa_patient_id}/{filename}"


class TPADocument(models.Model):
    tpa_patient = models.ForeignKey(TPAPatient, on_delete=models.CASCADE, related_name="documents")
    doc_type = models.CharField(max_length=20, choices=TPA_DOCUMENT_TYPE_CHOICES, default="other")
    file = models.FileField(upload_to=tpa_document_upload_path)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.get_doc_type_display()} -- {self.tpa_patient}"


class TPAImportMapping(models.Model):
    """
    Reusable column-mapping presets for the daily Excel import (e.g. the MAA
    Yojana TMS Case Status Tracker export). The exact export layout is not
    finalized yet, so mapping is entered by staff on each import and saved
    here under a name for reuse next time -- never hardcoded.
    """
    name = models.CharField(max_length=100, unique=True)
    mapping = models.JSONField(
        default=dict,
        help_text="{'target_field': 'Excel column header', ...}"
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class TPAImportBatch(models.Model):
    """One run of the 'Import TPA Update' Excel importer -- the audit header."""
    STATUS_CHOICES = [
        ("mapping", "Awaiting Column Mapping"),
        ("done", "Completed"),
        ("reverted", "Reverted"),
        ("failed", "Failed"),
    ]
    scheme_type = models.CharField(max_length=12, choices=TPA_SCHEME_TYPE_CHOICES, default="government")
    file = models.FileField(upload_to="tpa_imports/")
    original_filename = models.CharField(max_length=255, blank=True, default="")
    mapping = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="mapping")

    imported_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    imported_at = models.DateTimeField(auto_now_add=True)

    updated_count = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    merged_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True, default="")

    reverted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="tpa_batches_reverted")
    reverted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-imported_at"]
        verbose_name = "TPA Import Batch"
        verbose_name_plural = "TPA Import Batches"

    def __str__(self):
        return f"Import #{self.id} -- {self.imported_at:%d %b %Y %H:%M} by {self.imported_by}"

    @property
    def summary_text(self):
        merged = f", {self.merged_count} merged into another row's total" if self.merged_count else ""
        skipped = f", {self.skipped_count} skipped -- no match" if self.skipped_count else ""
        return f"{self.updated_count} updated, {self.created_count} new{merged}{skipped}"


class TPAImportRow(models.Model):
    """Per-row audit detail for a TPAImportBatch -- what matched, what changed."""
    ACTION_CHOICES = [
        ("updated", "Updated existing record"),
        ("created", "Created new draft record"),
        ("merged", "Merged into another row's total (same TID)"),
        ("skipped", "Skipped -- no match"),
        ("error", "Error"),
    ]
    MATCH_CHOICES = [
        ("tid", "Matched by TID"),
        ("policy_name", "Matched by Policy No. + Patient Name"),
        ("none", "No match"),
    ]

    batch = models.ForeignKey(TPAImportBatch, on_delete=models.CASCADE, related_name="rows")
    row_number = models.PositiveIntegerField()
    raw_data = models.JSONField(default=dict)

    match_type = models.CharField(max_length=15, choices=MATCH_CHOICES, default="none")
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    tpa_patient = models.ForeignKey(TPAPatient, on_delete=models.SET_NULL, null=True, blank=True, related_name="import_rows")

    field_changes = models.JSONField(
        default=dict, blank=True,
        help_text="{'field': {'before': ..., 'after': ...}, ...} -- used to trace/revert a bad import."
    )
    error_message = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["row_number"]

    def __str__(self):
        return f"Batch #{self.batch_id} row {self.row_number} -- {self.action}"

