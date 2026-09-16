from django.db import models
from .core import Patient, Department, Doctor, atc_code_validator

class Appointment(models.Model):
    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name="appointments"
    )
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name="appointments"
    )
    doctor = models.ForeignKey(
        Doctor, on_delete=models.PROTECT, related_name="appointments"
    )

    date = models.DateField()
    time = models.TimeField()
    purpose = models.TextField(blank=True)

    # ── BILLING ─────────────────────────────────────────
    fee          = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    payment_mode = models.CharField(
        max_length=10,
        choices=[("CASH", "Cash"), ("UPI", "UPI"), ("FREE", "Free")],
        default="CASH",
        blank=True,
    )
    is_paid = models.BooleanField(default=False)

    appointment_type = models.CharField(
        max_length=20,
        choices=[
            ("New", "New Case"),
            ("Follow-up", "Follow-up"),
            ("Emergency", "Emergency"),
            ("Procedure", "Procedure Review"),
        ],
        default="New",
    )

    status = models.CharField(
        max_length=20,
        choices=[
            ("Scheduled", "Scheduled"),
            ("Completed", "Completed"),
            ("Cancelled", "Cancelled"),
            ("No-show", "No Show"),
        ],
        default="Scheduled",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-time"]
        unique_together = ("doctor", "date", "time")

    def __str__(self):
        return f"{self.patient} - {self.date} {self.time}"


# ===================== ICD CODE =====================
class ICDCode(models.Model):
    CATEGORY_CHOICES = [
        ("post_op", "Post-op"),
        ("medical", "Medical"),
        ("surgical", "Surgical"),
        ("gynecology", "Gynecology"),
        ("orthopedics", "Orthopedics"),
        ("chest", "Chest"),
        ("cardiology", "Cardiology"),
        ("neurology", "Neurology"),
        ("urology", "Urology"),
    ]

    code        = models.CharField(max_length=10, unique=True)
    description = models.CharField(max_length=255)
    snomed_code = models.CharField(
        max_length=30, blank=True, null=True,
        help_text="SNOMED CT concept ID e.g. '73211009' for Diabetes mellitus"
    )
    snomed_description = models.CharField(
        max_length=255, blank=True, null=True,
        help_text="SNOMED CT preferred term e.g. 'Diabetes mellitus'"
    )
    sort_order = models.IntegerField(default=9999, null=True, blank=True)
    category = models.CharField(
        max_length=20, choices=CATEGORY_CHOICES, blank=True, default=""
    )

    class Meta:
        ordering = ["sort_order", "code"]

    def __str__(self):
        return f"{self.code} - {self.description}"


# ===================== CONSULTATION =====================
class Consultation(models.Model):
    appointment = models.OneToOneField(
        Appointment, on_delete=models.CASCADE, related_name="consultation"
    )

    # ===== VITAL SIGNS =====
    pulse  = models.CharField(max_length=10, blank=True)
    bp     = models.CharField(max_length=20, blank=True)
    spo2   = models.CharField(max_length=10, blank=True)
    weight = models.CharField(max_length=10, blank=True)

    # ===== QUICK LAB VALUES (manual entry, outside/patient-reported —
    # not linked to internal Lab Billing/Investigations) =====
    quick_lab_values = models.JSONField(blank=True, null=True, default=dict)
    usg_findings = models.TextField(blank=True)

    # ===== CLINICAL =====
    chief_complaints = models.TextField(blank=True)
    examination      = models.TextField(blank=True)
    procedures_performed = models.TextField(blank=True)
    symptoms         = models.ManyToManyField("Symptom", blank=True)
    signs            = models.ManyToManyField("Sign", blank=True)
    past_history     = models.ManyToManyField("PastHistory", blank=True)
    past_history_date = models.DateField(null=True, blank=True)
    surgical_history  = models.ManyToManyField("SurgicalHistory", blank=True)
    # Free-text entries typed under Chief Complaints / Examination Findings —
    # scoped to THIS consultation only, never written to the shared masters.
    custom_symptoms         = models.TextField(blank=True, default="")
    custom_signs            = models.TextField(blank=True, default="")
    surgery_date     = models.DateField(null=True, blank=True)
    diagnosis_text   = models.CharField(max_length=255, blank=True)
    diagnosis_icd    = models.ForeignKey(
        ICDCode, on_delete=models.SET_NULL, null=True, blank=True
    )
    icd_codes        = models.ManyToManyField(ICDCode, blank=True, related_name='consultations')
    ai_notes = models.TextField(blank=True, null=True)
    ai_investigation_input = models.TextField(blank=True)
    ai_probable_diagnosis = models.TextField(blank=True)
    ai_required_investigations = models.TextField(blank=True)

    # ===== AI CLINICAL SCRIBE =====
    # Doctor's rough shorthand notes, and the AI-structured note generated
    # from them (History/Examination/Diagnosis/Plan) — the doctor reviews
    # and edits the structured note before it is saved, same as every other
    # AI-assisted field on this model.
    scribe_raw_notes = models.TextField(blank=True)
    scribe_structured_note = models.TextField(blank=True)

    # ===== INVESTIGATIONS & LAB STATUS =====
    investigations = models.ManyToManyField("Investigation", blank=True)
    lab_advised    = models.BooleanField(default=False)

    # ===== ADVICE =====
    advice = models.TextField(blank=True)
    diet_advice = models.TextField(blank=True)

    # ===== FOLLOW-UP =====
    follow_up_date = models.DateField(null=True, blank=True)
    follow_up_type = models.CharField(
        max_length=50,
        choices=[
            ("review",          "Review"),
            ("suture_removal",  "Suture Removal"),
            ("report_check",    "Report Check"),
            ("emergency",       "If Symptoms Worsen"),
        ],
        blank=True,
    )
    follow_up_notes = models.TextField(blank=True)

    # ===== REFUSAL OF ADMISSION / LAMA CONSENT =====
    lama_declined = models.BooleanField(default=False)
    lama_diagnosis = models.CharField(max_length=255, blank=True)
    lama_plan = models.TextField(blank=True)
    lama_consent_en = models.TextField(blank=True)
    lama_consent_hi = models.TextField(blank=True)
    lama_attendant_name = models.CharField(max_length=150, blank=True)
    lama_attendant_relation = models.CharField(
        max_length=20,
        choices=[
            ("self",   "Self"),
            ("spouse", "Spouse"),
            ("parent", "Parent"),
            ("child",  "Child"),
            ("sibling", "Sibling"),
            ("other",  "Other"),
        ],
        blank=True,
    )
    lama_signed_name = models.CharField(max_length=150, blank=True)
    lama_signature_data = models.TextField(blank=True, null=True)
    lama_signed_at = models.DateTimeField(null=True, blank=True)

    # ===== REFERRAL NOTE =====
    referral_flag = models.BooleanField(default=False)
    referral_to = models.CharField(max_length=200, blank=True)
    referral_reason = models.TextField(blank=True)
    referral_type = models.CharField(
        max_length=20,
        choices=[
            ("investigation", "Investigation Referral"),
            ("treatment",     "Treatment Referral"),
        ],
        default="investigation",
        blank=True,
    )
    referral_urgency = models.CharField(
        max_length=20,
        choices=[
            ("routine",   "Routine"),
            ("urgent",    "Urgent"),
            ("emergency", "Emergency"),
        ],
        blank=True,
    )
    referral_letter_text = models.TextField(blank=True)

    # ===== MEDICAL CERTIFICATE (legacy, free-text/AI format) =====
    # Superseded 2026-09 by the fixed NMC Sickness/Fitness certificate
    # format below. Kept (not dropped) purely so the certificates already
    # issued under this format stay readable in the DB — no view writes to
    # these fields any more; new certificates use the NMC fields instead.
    certificate_no = models.CharField(max_length=30, blank=True)
    certificate_reason = models.CharField(
        max_length=20,
        choices=[
            ("post_procedure", "Post-Procedure Rest"),
            ("illness",         "Illness / Unfit for Duty"),
            ("fitness",         "Fitness Certificate"),
            ("other",           "Other"),
        ],
        blank=True,
    )
    certificate_reason_other = models.CharField(max_length=200, blank=True)
    certificate_text = models.TextField(blank=True)
    certificate_generated_at = models.DateTimeField(null=True, blank=True)

    # ===== MEDICAL CERTIFICATE — NMC Sickness/Leave & Fitness format =====
    # Fixed wording per the NMC Code of Medical Ethics Regulations 2002,
    # Appendix II. There is no free-text/AI-drafted body for this
    # certificate — only the blanks below are filled in and are printed
    # into the fixed template.
    certificate_part = models.CharField(
        max_length=6,
        choices=[
            ("A",    "Part A — Sickness / Leave"),
            ("B",    "Part B — Fitness"),
            ("both", "Both Parts"),
        ],
        blank=True,
    )
    sickness_diagnosis = models.CharField(max_length=255, blank=True)
    days_absent = models.PositiveSmallIntegerField(null=True, blank=True)
    absence_from_date = models.DateField(null=True, blank=True)
    absence_to_date = models.DateField(null=True, blank=True)
    fitness_effective_date = models.DateField(null=True, blank=True)
    place_of_examination = models.CharField(max_length=200, blank=True)
    date_of_issue = models.DateField(null=True, blank=True)

    # ===== METADATA =====
    custom_investigations = models.TextField(blank=True, null=True)
    last_modified_by = models.CharField(max_length=100, blank=True, null=True)
    created_at       = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Consultation for {self.appointment.patient.full_name}"


# =====================================================================
# INVESTIGATION CATEGORY
# =====================================================================
# ===================== PRESCRIPTION =====================
class Prescription(models.Model):
    consultation = models.ForeignKey(
        Consultation, on_delete=models.CASCADE, related_name="prescriptions"
    )
    medicine     = models.CharField(max_length=200)
    dose         = models.CharField(max_length=100)
    frequency    = models.CharField(max_length=50)
    duration     = models.CharField(max_length=50)
    instructions = models.CharField(max_length=200, blank=True)
    atc_code     = models.CharField(max_length=10, blank=True, null=True, default="",
                       validators=[atc_code_validator])

    def __str__(self):
        return self.medicine


