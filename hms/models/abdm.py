from django.db import models
from encrypted_model_fields.fields import EncryptedCharField
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


# ═══════════════════════════════════════════════════════
# ABDM M3 — HIU (HEALTH INFORMATION USER) MODELS
#
# Mirrors the M2 models above but for the opposite role: here WE are
# requesting a patient's records held by another facility, not sharing
# our own. See hms/abdm/services/hiu.py.
# ═══════════════════════════════════════════════════════

class ABDMConsentRequest(models.Model):
    """
    A consent request WE (as HIU) initiate to view a patient's records
    held by another facility (M3 doc §4.3.1). One request can result in
    multiple ABDMConsentArtefact rows -- one per HIP the patient grants,
    delivered via the notify callback (§4.3.3) after the patient acts on
    the request in their PHR app.
    """
    STATUS_CHOICES = [
        ("REQUESTED", "Requested"),
        ("GRANTED",   "Granted"),
        ("DENIED",    "Denied"),
        ("EXPIRED",   "Expired"),
        ("REVOKED",   "Revoked"),
    ]
    patient              = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="abdm_consent_requests")
    hip_id               = models.CharField(max_length=100, blank=True)  # blank = any HIP holding this patient's data
    purpose_code         = models.CharField(max_length=50, default="CAREMGT")
    purpose_text         = models.CharField(max_length=255, default="Care Management")
    hi_types             = models.JSONField(default=list)
    date_from            = models.DateTimeField()
    date_to              = models.DateTimeField()
    requester_name       = models.CharField(max_length=255)
    requester_id_type    = models.CharField(max_length=50, blank=True)
    requester_id_value   = models.CharField(max_length=100, blank=True)
    requester_id_system  = models.CharField(max_length=255, blank=True)
    # Our own REQUEST-ID sent on the /consent/request/init call -- the
    # on-init callback's response.requestId is matched against this to
    # fill in consent_request_id below.
    request_id           = models.CharField(max_length=100, unique=True)
    consent_request_id   = models.CharField(max_length=100, blank=True)
    status                = models.CharField(max_length=20, choices=STATUS_CHOICES, default="REQUESTED")
    created_at            = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "ABDM Consent Request (HIU)"
        verbose_name_plural = "ABDM Consent Requests (HIU)"
        ordering            = ["-created_at"]

    def __str__(self):
        return f"ConsentRequest({self.patient}) — {self.status}"


class ABDMConsentArtefact(models.Model):
    """
    One consent artefact granted for a ABDMConsentRequest -- one per HIP
    the patient approved (M3 doc §4.3.3/§4.3.8). Created as a
    status="FETCHING" stub the moment HIUService.fetch_artefact() is
    called (before the artefact's own consent_id is known to have full
    details), then filled in by the on-fetch callback, matched by
    consent_id.
    """
    consent_request = models.ForeignKey(ABDMConsentRequest, on_delete=models.CASCADE, related_name="artefacts")
    consent_id      = models.CharField(max_length=100, unique=True)
    hip_id          = models.CharField(max_length=100, blank=True)
    hi_types        = models.JSONField(default=list)
    date_from       = models.DateTimeField(null=True, blank=True)
    date_to         = models.DateTimeField(null=True, blank=True)
    status          = models.CharField(max_length=20, default="FETCHING")
    raw_artefact    = models.TextField(blank=True)  # full on-fetch JSON, for audit/signature verification later
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "ABDM Consent Artefact (HIU)"
        verbose_name_plural = "ABDM Consent Artefacts (HIU)"
        ordering            = ["-created_at"]

    def __str__(self):
        return f"ConsentArtefact({self.consent_id}) — {self.hip_id}"


class ABDMHealthInformationRequest(models.Model):
    """
    Tracks one data-request transaction WE (as HIU) initiate against a
    granted consent artefact (M3 doc §5.3.1). Stores our own ephemeral
    Fidelius key material so the later, asynchronous data push to our
    dataPushUrl can be decrypted -- see HIUService.request_health_information
    and the handler for that dataPushUrl.
    """
    STATUS_CHOICES = [
        ("REQUESTED", "Requested"),
        ("RECEIVED",  "Received"),
        ("FAILED",    "Failed"),
    ]
    consent_artefact = models.ForeignKey(ABDMConsentArtefact, on_delete=models.CASCADE, related_name="hi_requests")
    # Filled in once the CM's on-request callback (§5.3.2) assigns one;
    # blank between the initial request and that callback.
    transaction_id   = models.CharField(max_length=100, unique=True, blank=True, null=True)
    # Our own REQUEST-ID for the /health-information/request call itself.
    request_id       = models.CharField(max_length=100, unique=True)
    our_private_key  = models.CharField(max_length=100)   # base64 -- kept only long enough to decrypt the incoming push
    our_public_key   = models.CharField(max_length=600)
    our_nonce        = models.CharField(max_length=100)
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default="REQUESTED")
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "ABDM Health Information Request (HIU)"
        verbose_name_plural = "ABDM Health Information Requests (HIU)"
        ordering            = ["-created_at"]

    def __str__(self):
        return f"HIRequest({self.transaction_id or self.request_id}) — {self.status}"


class ABDMReceivedRecord(models.Model):
    """
    One decrypted FHIR bundle received from a HIP, for a
    ABDMHealthInformationRequest (M3 doc §5.3.2's data push payload).
    """
    hi_request              = models.ForeignKey(ABDMHealthInformationRequest, on_delete=models.CASCADE, related_name="records")
    care_context_reference  = models.CharField(max_length=100)
    hi_status               = models.CharField(max_length=20, default="OK")  # OK | ERRORED
    fhir_bundle              = models.TextField(blank=True)  # decrypted JSON, blank if hi_status=ERRORED
    error_detail             = models.CharField(max_length=255, blank=True)
    received_at              = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "ABDM Received Record (HIU)"
        verbose_name_plural = "ABDM Received Records (HIU)"
        ordering            = ["-received_at"]

    def __str__(self):
        return f"ReceivedRecord({self.care_context_reference})"


# ═══════════════════════════════════════════════════════
# ABDM M1 — SCAN & SHARE
# ═══════════════════════════════════════════════════════

class ABDMScanShare(models.Model):
    """
    One profile share from a patient who scanned the hospital's ABDM QR code
    at a counter (V3 POST /api/v3/hip/patient/share). We match or create the
    Patient, issue a same-day queue token, and reply via on-share.
    """
    STATUS_CHOICES = [
        ("WAITING", "Waiting"),
        ("DONE",    "Done"),
    ]

    request_id     = models.CharField(max_length=100, blank=True)
    hip_id         = models.CharField(max_length=50, blank=True)
    context        = models.CharField(max_length=100, blank=True)  # counter code from the QR
    abha_number    = EncryptedCharField(max_length=20, blank=True, null=True)
    abha_address   = EncryptedCharField(max_length=100, blank=True, null=True)
    name           = models.CharField(max_length=150, blank=True)
    gender         = models.CharField(max_length=10, blank=True)
    year_of_birth  = models.CharField(max_length=4, blank=True)
    month_of_birth = models.CharField(max_length=2, blank=True)
    day_of_birth   = models.CharField(max_length=2, blank=True)
    phone_number   = models.CharField(max_length=20, blank=True)
    address_line   = models.CharField(max_length=255, blank=True)
    district       = models.CharField(max_length=100, blank=True)
    state          = models.CharField(max_length=100, blank=True)
    pincode        = models.CharField(max_length=10, blank=True)

    patient         = models.ForeignKey(Patient, on_delete=models.SET_NULL, null=True, blank=True, related_name="scan_shares")
    patient_created = models.BooleanField(default=False)
    token_number    = models.CharField(max_length=10, blank=True)
    token_date      = models.DateField(db_index=True)
    status          = models.CharField(max_length=10, choices=STATUS_CHOICES, default="WAITING")
    on_share_sent   = models.BooleanField(default=False)
    on_share_error  = models.CharField(max_length=255, blank=True)
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "ABDM Scan & Share"
        verbose_name_plural = "ABDM Scan & Share"
        ordering            = ["-created_at"]

    def __str__(self):
        return f"Token {self.token_number} — {self.name} ({self.token_date})"
