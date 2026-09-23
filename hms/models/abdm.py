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
    # The 7 hiTypes ABDM actually defines (M2 doc §4.3.3) — "OPDischargeNote"
    # used here previously isn't a real ABDM hiType at all.
    HI_TYPE_CHOICES = [
        ("Prescription",        "Prescription"),
        ("DiagnosticReport",    "Diagnostic Report (Lab/USG)"),
        ("OPConsultation",      "OPD Consultation"),
        ("DischargeSummary",    "Discharge Summary"),
        ("ImmunizationRecord",  "Immunization Record"),
        ("HealthDocumentRecord","Health Document Record"),
        ("WellnessRecord",      "Wellness Record"),
    ]

    patient          = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="care_contexts")
    reference_number = models.CharField(max_length=100)
    display          = models.CharField(max_length=255)
    hi_type          = models.CharField(
        max_length=50,
        choices=HI_TYPE_CHOICES,
        default="OPConsultation",
    )
    linked             = models.BooleanField(default=False)
    linked_at          = models.DateTimeField(null=True, blank=True)
    # Set while a "linking care context" call is in flight, matched against
    # the on_carecontext callback's response.requestId; cleared once that
    # callback confirms (linked=True) or errors (left linked=False, so the
    # next save attempt retries the link).
    pending_request_id = models.CharField(max_length=100, blank=True)
    created_at         = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name    = "Care Context"
        verbose_name_plural = "Care Contexts"
        unique_together = ("patient", "reference_number")

    def __str__(self):
        return f"{self.reference_number} — {self.patient}"


class ABDMLinkToken(models.Model):
    """
    Tracks a pending "generate link token" request (M2 doc §4.3.1/4.3.2).
    The token is NOT returned synchronously -- it arrives later via the
    on-generate-token callback, matched back to this row by request_id.
    """
    patient      = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="abdm_link_tokens")
    abha_address = models.CharField(max_length=100, blank=True)
    request_id   = models.CharField(max_length=100, unique=True)
    token        = models.TextField(blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    received_at  = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name        = "ABDM Link Token"
        verbose_name_plural = "ABDM Link Tokens"
        ordering            = ["-created_at"]

    def __str__(self):
        state = "received" if self.token else "pending"
        return f"LinkToken({self.abha_address}) — {state}"


class ABDMLinkingSession(models.Model):
    """
    Tracks one user-initiated-linking OTP round (M2 doc §5.3.5-5.3.12,
    a separate flow from HIP-initiated linking above -- here the PATIENT
    starts from a PHR app, HIE-CM calls us to init/confirm the link).
    We generate link_reference and otp during on-init; HIE-CM relays the
    patient-entered otp back via the confirm callback, matched by
    link_reference (ABDM's "linkRefNumber").
    """
    transaction_id = models.CharField(max_length=100)
    link_reference = models.CharField(max_length=100, unique=True)
    patient        = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="abdm_linking_sessions")
    otp            = models.CharField(max_length=10)
    created_at     = models.DateTimeField(auto_now_add=True)
    confirmed_at   = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name        = "ABDM Linking Session"
        verbose_name_plural = "ABDM Linking Sessions"
        ordering            = ["-created_at"]

    def __str__(self):
        return f"LinkingSession({self.patient}) — {self.link_reference}"


