from django.db import models
from .core import Patient


# ═══════════════════════════════════════════════════════
# ABDM M2 — CONSENT & CARE CONTEXT MODELS
# ═══════════════════════════════════════════════════════

class ABDMConsent(models.Model):
    consent_id   = models.CharField(max_length=100, unique=True)
    patient_abha = models.CharField(max_length=50, blank=True)
    status       = models.CharField(
        max_length=20,
        choices=[
            ("GRANTED", "Granted"),
            ("REVOKED", "Revoked"),
            ("EXPIRED", "Expired"),
            ("DENIED",  "Denied"),
        ],
        default="GRANTED"
    )
    hi_types    = models.TextField(blank=True)
    artifact    = models.TextField(blank=True)
    date_from   = models.CharField(max_length=50, blank=True)
    date_to     = models.CharField(max_length=50, blank=True)
    expire_at   = models.CharField(max_length=50, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "ABDM Consent"
        verbose_name_plural = "ABDM Consents"
        ordering            = ["-received_at"]

    def __str__(self):
        return f"{self.consent_id} — {self.patient_abha} ({self.status})"


class ABDMCareContext(models.Model):
    patient          = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="care_contexts")
    reference_number = models.CharField(max_length=100)
    display          = models.CharField(max_length=255)
    hi_type          = models.CharField(
        max_length=50,
        choices=[
            ("OPDischargeNote",  "OPD Consultation"),
            ("DiagnosticReport", "Lab Report"),
            ("Prescription",     "Prescription"),
            ("DischargeSummary", "Discharge Summary"),
        ],
        default="OPDischargeNote"
    )
    linked     = models.BooleanField(default=False)
    linked_at  = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name    = "Care Context"
        verbose_name_plural = "Care Contexts"
        unique_together = ("patient", "reference_number")

    def __str__(self):
        return f"{self.reference_number} — {self.patient}"


