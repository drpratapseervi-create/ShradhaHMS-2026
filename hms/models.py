import os
import re
from encrypted_model_fields.fields import EncryptedCharField
from auditlog.registry import auditlog
from django.db import models
from django.core.validators import RegexValidator, FileExtensionValidator
from django.utils import timezone
from datetime import date, timedelta, datetime
from django.contrib.auth.models import User
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

# WHO ATC codes always start with a letter (e.g. 'N02BE01'); drug strength
# values like "250+10mg" start with a digit — this catches that mix-up.
atc_code_validator = RegexValidator(
    regex=r'^[A-Za-z][A-Za-z0-9]*$',
    message="Enter a valid ATC code (e.g. 'N02BE01'), not a drug strength.",
)

# ===================== PATIENT =====================
class Patient(models.Model):

    # ==========================
    # NABH IDENTIFICATION
    # ==========================
    uhid = models.CharField(max_length=20, unique=True, blank=True)
    registration_datetime = models.DateTimeField(auto_now_add=True)
    full_name = models.CharField(max_length=150)
    date_of_birth = models.DateField(null=True, blank=True)
    age_years = models.PositiveSmallIntegerField(blank=True, null=True)

    @property
    def age(self):
        if self.date_of_birth:
            today = date.today()
            return today.year - self.date_of_birth.year - (
                (today.month, today.day) <  
                (self.date_of_birth.month, self.date_of_birth.day)
            )
        return self.age_years

    gender = models.CharField(
        max_length=10,
        choices=[
            ("Male", "Male"),
            ("Female", "Female"),
            ("Other", "Other"),
        ],
    )

    mobile_no = models.CharField(max_length=20)
    email = models.EmailField(blank=True, null=True)

    address = models.TextField()
    city = models.CharField(max_length=100, blank=True, null=True)
    district = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    pincode = models.CharField(max_length=10, blank=True, null=True)

    # ==========================
    # IDENTITY
    # ==========================
    father_or_husband_name = models.CharField(max_length=150, blank=True, null=True)

    id_proof_type = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        choices=[
            ("Aadhaar", "Aadhaar"),
            ("PAN", "PAN"),
            ("Voter ID", "Voter ID"),
            ("Driving License", "Driving License"),
        ],
    )

    # ✅ ENCRYPTED — Aadhaar/PAN number stored encrypted in DB
    id_proof_number = EncryptedCharField(max_length=50, blank=True, null=True)

    emergency_contact_person = models.CharField(max_length=150, blank=True, null=True)
    emergency_contact_number = models.CharField(max_length=20, blank=True, null=True)

    # ==========================
    # MEDICAL SAFETY
    # ==========================
    blood_group = models.CharField(
        max_length=5,
        blank=True,
        null=True,
        choices=[
            ("A+", "A+"), ("A-", "A-"),
            ("B+", "B+"), ("B-", "B-"),
            ("O+", "O+"), ("O-", "O-"),
            ("AB+", "AB+"), ("AB-", "AB-"),
        ],
    )

    allergy = models.BooleanField(default=False)
    allergy_details = models.TextField(blank=True, null=True)
    chronic_illness = models.TextField(blank=True, null=True)
    high_risk = models.BooleanField(default=False)

    # ==========================
    # ABHA — ✅ ENCRYPTED fields
    # ==========================
    abha_number  = EncryptedCharField(max_length=20, blank=True, null=True)
    abha_address = EncryptedCharField(max_length=100, blank=True, null=True)
    abha_verified = models.BooleanField(default=False)
    abha_consent  = models.BooleanField(default=False)

    # ==========================
    # LEGAL
    # ==========================
    consent_given = models.BooleanField(default=False)
    consent_timestamp = models.DateTimeField(blank=True, null=True)

    # ==========================
    # SAVE LOGIC
    # ==========================
    def save(self, *args, **kwargs):
        is_new = not self.pk
        if is_new:
            super().save(*args, **kwargs)
            # The first save already inserted the row and assigned self.pk;
            # force_insert must not carry over or the second save below
            # will attempt to INSERT the same pk again and collide.
            kwargs.pop("force_insert", None)

        if not self.uhid:
            self.uhid = f"SH{self.id:06d}"

        if self.age and self.age >= 60:
            self.high_risk = True
        else:
            self.high_risk = False

        if self.consent_given and not self.consent_timestamp:
            self.consent_timestamp = timezone.now()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} ({self.uhid})"


# ===================== DEPARTMENT =====================
class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return self.name


# ===================== DOCTOR =====================
class Doctor(models.Model):
    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name="doctors",
        null=True,
        blank=True,
    )
    full_name = models.CharField(max_length=120)
    specialization = models.CharField(max_length=120, blank=True)
    op_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    qualification = models.CharField(
        max_length=120, blank=True,
        help_text="e.g. MBBS, MS -- printed on report signature lines"
    )
    registration_no = models.CharField(
        max_length=50, blank=True,
        help_text="e.g. RMC No-27994 -- printed on report signature lines"
    )

    def __str__(self):
        if self.department:
            return f"{self.full_name} ({self.department.name})"
        return self.full_name


# ===================== APPOINTMENT =====================
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


# ===================== INVESTIGATION PARAMETER =====================
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


# ===================== SYMPTOM =====================
class Symptom(models.Model):
    name       = models.CharField(max_length=200)
    department = models.ForeignKey(
        Department, on_delete=models.CASCADE, related_name="symptoms"
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=9999, blank=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


# ===================== SIGN =====================
class Sign(models.Model):
    name       = models.CharField(max_length=200)
    department = models.ForeignKey(
        Department, on_delete=models.CASCADE, related_name="signs"
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=9999, blank=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


# ===================== PAST HISTORY =====================
class PastHistory(models.Model):
    name      = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


# ===================== SURGICAL HISTORY =====================
class SurgicalHistory(models.Model):
    name      = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


# ===================== ADVICE OPTION =====================
class AdviceOption(models.Model):
    text       = models.CharField(max_length=200)
    is_active  = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.text


# ===================== DIET ADVICE OPTION =====================
class DietAdviceOption(models.Model):
    text       = models.CharField(max_length=200)
    is_active  = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.text


# ===================== FOLLOW-UP NOTE PHRASE =====================
class FollowUpNotePhrase(models.Model):
    text       = models.CharField(max_length=200)
    is_active  = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.text


# ===================== MEDICAL IMAGE =====================
class MedicalImage(models.Model):

    IMAGE_TYPE_CHOICES = [
        ("XRAY",      "X-Ray"),
        ("USG",       "Ultrasound (USG)"),
        ("ENDOSCOPY", "Endoscopy"),
        ("OT",        "OT Image"),
        ("ECG",       "ECG"),
        ("CT",        "CT Scan"),
        ("MRI",       "MRI"),
        ("OTHER",     "Other"),
    ]

    patient = models.ForeignKey(
        "Patient", on_delete=models.CASCADE, related_name="medical_images",
    )
    consultation = models.ForeignKey(
        "Consultation", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="medical_images",
    )
    image_type  = models.CharField(max_length=50, choices=IMAGE_TYPE_CHOICES, default="XRAY")
    title       = models.CharField(max_length=200)
    image       = models.ImageField(upload_to="medical_images/", blank=True, null=True)
    report_text = models.TextField(blank=True, null=True)
    uploaded_by = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    # ✅ NEW — DICOM fields
    dicom_instance_id = models.CharField(
        max_length=100, blank=True, null=True,
        help_text="Orthanc DICOM instance ID"
    )
    is_dicom = models.BooleanField(
        default=False,
        help_text="True if stored in Orthanc DICOM server"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.patient.full_name} - {self.image_type} - {self.title}"

# ===================== WARD & BED =====================
class Ward(models.Model):
    name       = models.CharField(max_length=100)
    total_beds = models.IntegerField()

    def __str__(self):
        return self.name


class Bed(models.Model):
    ward       = models.ForeignKey(Ward, on_delete=models.CASCADE)
    bed_number = models.CharField(max_length=10)
    is_occupied = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.ward.name} - Bed {self.bed_number}"


# ===================== IPD ADMISSION =====================
class IPDAdmission(models.Model):

    patient    = models.ForeignKey("Patient",     on_delete=models.CASCADE)
    ward       = models.ForeignKey("Ward",        on_delete=models.SET_NULL, null=True, blank=True)
    bed        = models.ForeignKey("Bed",         on_delete=models.SET_NULL, null=True, blank=True)
    doctor     = models.ForeignKey("Doctor",      on_delete=models.SET_NULL, null=True, blank=True)
    department = models.ForeignKey("Department",  on_delete=models.SET_NULL, null=True, blank=True)

    ipd_no         = models.CharField(max_length=20, unique=True, blank=True, null=True)
    admission_date = models.DateTimeField(default=timezone.now)

    # -------- CLINICAL DATA --------
    chief_complaint = models.TextField(blank=True)
    symptoms        = models.TextField(blank=True)
    diagnosis       = models.TextField(blank=True, null=True)
    treatment_plan  = models.TextField(blank=True)
    icd_code        = models.CharField(max_length=10, blank=True)

    # -------- PROCEDURE / COURSE --------
    general_examination     = models.TextField(blank=True)
    local_examination       = models.TextField(blank=True)
    procedure_done          = models.TextField(blank=True)
    ipd_treatment           = models.TextField(blank=True,
        help_text="Inpatient Medication Chart narrative — IV/inpatient treatment given during the stay")
    course_in_hospital      = models.TextField(blank=True)
    condition_at_discharge  = models.TextField(blank=True)
    treatment_on_discharge  = models.TextField(blank=True)

    # -------- INVESTIGATIONS (DISCHARGE SUMMARY) --------
    inv_hb              = models.CharField("Hb", max_length=30, blank=True)
    inv_tlc             = models.CharField("TLC", max_length=30, blank=True)
    inv_platelet_count  = models.CharField("Platelet Count", max_length=30, blank=True)
    inv_rbs             = models.CharField("RBS (mg/dl)", max_length=30, blank=True)
    inv_hiv             = models.CharField("HIV", max_length=30, blank=True)
    inv_hbsag           = models.CharField("HbsAg", max_length=30, blank=True)
    inv_usg             = models.CharField("USG", max_length=100, blank=True)

    # -------- DISCHARGE --------
    discharge_summary       = models.TextField(blank=True)
    discharge_advice        = models.TextField(blank=True)
    follow_up_date          = models.DateField(null=True, blank=True)
    follow_up_instructions  = models.TextField(blank=True)
    discharge_instructions  = models.TextField(blank=True)
    discharge_date          = models.DateTimeField(null=True, blank=True)

    # -------- ATTENDANT --------
    attendant_name     = models.CharField(max_length=100, blank=True)
    attendant_relation = models.CharField(max_length=50, blank=True)
    attendant_mobile   = models.CharField(max_length=15, blank=True)

    # -------- STATUS --------
    status = models.CharField(
        max_length=20,
        choices=[("ADMITTED", "Admitted"), ("DISCHARGED", "Discharged")],
        default="ADMITTED"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.ipd_no:
            last = IPDAdmission.objects.exclude(ipd_no__isnull=True).order_by("id").last()
            number = (int(last.ipd_no.split("-")[-1]) + 1) if last and last.ipd_no else 1
            self.ipd_no = f"IPD-{number:05d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.ipd_no} - {self.patient.full_name}"


# ===================== IPD VITALS =====================
class IPDVital(models.Model):
    admission   = models.ForeignKey(IPDAdmission, on_delete=models.CASCADE)
    pulse       = models.IntegerField(null=True, blank=True)
    bp          = models.CharField(max_length=20, blank=True)
    temperature = models.FloatField(null=True, blank=True)
    spo2        = models.IntegerField(null=True, blank=True)
    rr          = models.IntegerField(null=True, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.admission.ipd_no} - {self.recorded_at}"


# ===================== IPD MEDICATION =====================
class IPDMedication(models.Model):
    admission     = models.ForeignKey(IPDAdmission, on_delete=models.CASCADE)
    drug          = models.ForeignKey(
        'DrugMaster', on_delete=models.SET_NULL, null=True, blank=True,
        related_name="ipd_medications"
    )
    medicine_name = models.CharField(max_length=200)
    dose          = models.CharField(max_length=50, blank=True)
    route         = models.CharField(max_length=50, blank=True)
    frequency     = models.CharField(max_length=50, blank=True)
    start_date    = models.DateField(auto_now_add=True)

    def __str__(self):
        return f"{self.medicine_name} - {self.admission.ipd_no}"


# ===================== IPD DISCHARGE MEDICATION =====================
class IPDDischargeMedication(models.Model):
    admission     = models.ForeignKey(
        IPDAdmission, on_delete=models.CASCADE, related_name="discharge_medications"
    )
    drug          = models.ForeignKey(
        'DrugMaster', on_delete=models.SET_NULL, null=True, blank=True,
        related_name="ipd_discharge_medications"
    )
    medicine_name = models.CharField(max_length=200)
    dose          = models.CharField(max_length=50, blank=True)
    route         = models.CharField(max_length=50, blank=True)
    frequency     = models.CharField(max_length=50, blank=True)
    duration      = models.CharField(max_length=50, blank=True)
    instructions  = models.CharField(max_length=200, blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.medicine_name} - {self.admission.ipd_no}"


# ===================== DISCHARGE TEMPLATES =====================
class DischargeTemplate(models.Model):
    GENDER_CHOICES = [("M", "Male"), ("F", "Female"), ("U", "Any")]

    procedure_name          = models.CharField(max_length=150)
    gender                  = models.CharField(max_length=1, choices=GENDER_CHOICES, default="U")
    diagnosis                = models.TextField(blank=True)
    chief_complaints         = models.TextField(blank=True)
    general_examination      = models.TextField(blank=True)
    local_examination        = models.TextField(blank=True)
    operation_notes           = models.TextField(blank=True)
    course_in_hospital        = models.TextField(blank=True)
    treatment_on_discharge    = models.TextField(blank=True)
    advice                     = models.TextField(blank=True)
    follow_up                   = models.TextField(blank=True)
    instructions                 = models.TextField(blank=True)
    is_active                     = models.BooleanField(default=True)
    created_at                     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["procedure_name", "gender"]
        unique_together = [("procedure_name", "gender")]

    def __str__(self):
        return f"{self.procedure_name} ({self.get_gender_display()})"


# ===================== IPD PROGRESS NOTES =====================
class IPDProgressNote(models.Model):
    admission  = models.ForeignKey(
        IPDAdmission, on_delete=models.CASCADE, related_name="progress_notes"
    )
    doctor     = models.ForeignKey(Doctor, on_delete=models.SET_NULL, null=True, blank=True)
    date_time  = models.DateTimeField(auto_now_add=True)
    subjective = models.TextField(blank=True)
    objective  = models.TextField(blank=True)
    assessment = models.TextField(blank=True)
    plan       = models.TextField(blank=True)

    class Meta:
        ordering = ["-date_time"]

    def __str__(self):
        return f"Progress Note - {self.admission.ipd_no}"


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


# ===================== USER PROFILE =====================
class UserProfile(models.Model):
    ROLE_CHOICES = [
        ("admin",      "Admin"),
        ("doctor",     "Doctor"),
        ("nursing",    "Nursing Staff"),
        ("laboratory", "Laboratory"),
        ("reception",  "Reception"),
    ]

    user      = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role      = models.CharField(max_length=20, choices=ROLE_CHOICES, default="reception")
    full_name = models.CharField(max_length=100, blank=True)
    phone     = models.CharField(max_length=15, blank=True)
    is_active = models.BooleanField(default=True)
    doctor    = models.OneToOneField(
        "Doctor", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="user_profile"
    )

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

    class Meta:
        verbose_name        = "User Profile"
        verbose_name_plural = "User Profiles"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()


# ===================== EXPENSE =====================
class Expense(models.Model):
    date    = models.DateField(auto_now_add=True)
    title   = models.CharField(max_length=200)
    amount  = models.DecimalField(max_digits=10, decimal_places=2)
    remarks = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.title


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


# ===================== OT =====================
class OTBooking(models.Model):
    patient     = models.ForeignKey("Patient", on_delete=models.CASCADE)
    uhid        = models.CharField(max_length=20)
    surgeon     = models.CharField(max_length=100)
    assistant   = models.CharField(max_length=100, blank=True, null=True)
    anesthetist = models.CharField(max_length=100)
    procedure   = models.CharField(max_length=200)
    ot_date     = models.DateField()
    ot_time     = models.TimeField()
    ot_room     = models.CharField(max_length=50)
    case_type   = models.CharField(
        max_length=20,
        choices=[("Elective", "Elective"), ("Emergency", "Emergency")]
    )
    anesthesia_type = models.CharField(
        max_length=20,
        choices=[("GA", "GA"), ("SA", "SA"), ("LA", "LA")]
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ("Scheduled",  "Scheduled"),
            ("Completed",  "Completed"),
            ("Cancelled",  "Cancelled"),
        ],
        default="Scheduled"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.patient} - {self.procedure}"


class OTNotes(models.Model):
    booking           = models.OneToOneField(OTBooking, on_delete=models.CASCADE)
    start_time        = models.TimeField()
    end_time          = models.TimeField()
    findings          = models.TextField()
    procedure_done    = models.TextField()
    complications     = models.TextField(blank=True, null=True)
    blood_loss        = models.CharField(max_length=50, blank=True)
    post_op_condition = models.TextField()
    created_at        = models.DateTimeField(auto_now_add=True)


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


# =====================================================================
# DOCUMENT MANAGEMENT
# =====================================================================

def document_upload_path(instance, filename):
    return f'hospital_documents/{instance.category}/{filename}'


HOSPITAL_DOC_TYPES = [
    ('hospital_certification',  'Hospital Certification'),
    ('pollution_noc',           'Pollution NOC'),
    ('bmw_udyog',               'BMW / Udyog Certificate'),
    ('clinical_establishment',  'Clinical Establishment Certificate'),
    ('fire_noc',                'Fire NOC'),
    ('hospital_pan',            'Hospital PAN Card'),
    ('bank_details',            'Bank Details Document'),
    ('other_hospital',          'Other'),
]

DOCTOR_DOC_TYPES = [
    ('doctor_aadhaar',   'Aadhaar Card'),
    ('doctor_pan',       'PAN Card'),
    ('medical_council',  'Medical Council Certificate'),
    ('abdm_doctor',      'Professional Health ID (ABDM)'),
    ('other_doctor',     'Other'),
]

STAFF_DOC_TYPES = [
    ('staff_aadhaar',       'Aadhaar Card'),
    ('staff_pan',           'PAN Card'),
    ('degree_certificate',  'Degree Certificate'),
    ('nursing_certificate', 'Nursing Certificate'),
    ('abdm_staff',          'Professional Health ID (ABDM)'),
    ('other_staff',         'Other'),
]

EQUIPMENT_DOC_TYPES = [
    ('xray',               'X-Ray'),
    ('carm',               'C-ARM'),
    ('lab_machine',        'Lab Machine'),
    ('anaesthetic_machine','Anaesthetic Machine'),
    ('ecg',                'ECG Machine'),
    ('defibrillator',      'Defibrillator'),
    ('ot_light',           'OT Light'),
    ('autoclave',          'Autoclave'),
    ('other_equipment',    'Other Equipment'),
]

DOC_CATEGORY_CHOICES = [
    ('hospital',  'Hospital'),
    ('doctor',    'Doctor'),
    ('staff',     'Staff'),
    ('equipment', 'Equipment AMC / Certificate'),
]

ALL_DOC_TYPE_CHOICES = (
    HOSPITAL_DOC_TYPES + DOCTOR_DOC_TYPES + STAFF_DOC_TYPES + EQUIPMENT_DOC_TYPES
)


class HospitalDocument(models.Model):
    category       = models.CharField(max_length=20, choices=DOC_CATEGORY_CHOICES)
    doc_type       = models.CharField(max_length=60, choices=ALL_DOC_TYPE_CHOICES)
    title          = models.CharField(max_length=200)
    person_name    = models.CharField(max_length=150, blank=True, null=True,
                                      help_text="Doctor or staff member name")
    equipment_name = models.CharField(max_length=150, blank=True, null=True,
                                      help_text="Equipment name / serial number")
    issued_by      = models.CharField(max_length=200, blank=True, null=True,
                                      verbose_name="Issuing Authority")
    issue_date     = models.DateField(null=True, blank=True)
    expiry_date    = models.DateField(null=True, blank=True)
    document_file  = models.FileField(
        upload_to=document_upload_path, null=True, blank=True,
        verbose_name="Upload File (PDF / Image)"
    )
    notes      = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering        = ['category', 'expiry_date']
        verbose_name    = 'Hospital Document'
        verbose_name_plural = 'Hospital Documents'

    def __str__(self):
        return f"{self.get_category_display()} — {self.title}"

    @property
    def expiry_status(self):
        if not self.expiry_date:
            return 'no_expiry'
        today = timezone.now().date()
        if self.expiry_date < today:
            return 'expired'
        elif self.expiry_date <= today + timedelta(days=30):
            return 'expiring_soon'
        return 'valid'

    @property
    def days_to_expiry(self):
        if self.expiry_date:
            return (self.expiry_date - timezone.now().date()).days
        return None


# =====================================================================
# AUDIT LOG REGISTRATION
# =====================================================================
auditlog.register(Patient)
auditlog.register(Consultation)
auditlog.register(IPDAdmission)
auditlog.register(Prescription)
auditlog.register(InvestigationBill)
auditlog.register(InvestigationResult)
auditlog.register(DischargeBill)
auditlog.register(ICDCode)

# =====================================================================
# CONSTRUCTION EXPENSE MODELS
# =====================================================================

EXPENSE_HEAD_CHOICES = [
    # ── CIVIL & STRUCTURE ──
    ('Soil Removal / Excavation',  'Soil Removal / Excavation'),
    ('Soil Transport',             'Soil Transport'),
    ('PCC Work',                   'PCC Work'),
    ('RCC Work',                   'RCC Work'),
    ('Raft Foundation',            'Raft Foundation'),
    ('Brickwork / Masonry',        'Brickwork / Masonry'),
    ('Concrete / RMC',             'Concrete / RMC'),
    ('Shuttering / Formwork',      'Shuttering / Formwork'),
    ('Stone Work',                 'Stone Work'),
    ('Civil Work (General)',       'Civil Work (General)'),

    # ── RAW MATERIALS ──
    ('Cement',                     'Cement'),
    ('Steel / TMT Bars',           'Steel / TMT Bars'),
    ('Sand',                       'Sand'),
    ('Bricks',                     'Bricks'),
    ('Stone / Gitti / Aggregate',  'Stone / Gitti / Aggregate'),
    ('RMC (Ready Mix Concrete)',   'RMC (Ready Mix Concrete)'),
    ('Fly Ash',                    'Fly Ash'),
    ('Waterproofing Material',     'Waterproofing Material'),

    # ── FINISHING ──
    ('Tiles',                      'Tiles'),
    ('Granite / Marble',           'Granite / Marble'),
    ('Paint',                      'Paint'),
    ('Plaster Work',               'Plaster Work'),
    ('False Ceiling',              'False Ceiling'),
    ('POP / Gypsum Work',          'POP / Gypsum Work'),

    # ── SERVICES ──
    ('Electrical Work',            'Electrical Work'),
    ('Wiring & Conduit',           'Wiring & Conduit'),
    ('Electrical Fittings',        'Electrical Fittings'),
    ('Plumbing Work',              'Plumbing Work'),
    ('Plumbing Material',          'Plumbing Material'),
    ('AC Ducting / HVAC',          'AC Ducting / HVAC'),
    ('Fire Safety / Sprinkler',    'Fire Safety / Sprinkler'),
    ('Lift / Elevator',            'Lift / Elevator'),

    # ── DOORS, WINDOWS & FRAMES ──
    ('Doors',                      'Doors'),
    ('Windows',                    'Windows'),
    ('Aluminium / UPVC Work',      'Aluminium / UPVC Work'),
    ('Grills & Railings',          'Grills & Railings'),

    # ── FURNITURE & FIXTURES ──
    ('Furniture',                  'Furniture'),
    ('Modular Kitchen / Cabinets', 'Modular Kitchen / Cabinets'),
    ('Hospital Furniture',         'Hospital Furniture'),
    ('Curtains / Blinds',          'Curtains / Blinds'),

    # ── SPECIAL AREAS ──
    ('OT Construction',            'OT Construction'),
    ('Labour Room Construction',   'Labour Room Construction'),
    ('ICU Construction',           'ICU Construction'),
    ('Reception Work',             'Reception Work'),
    ('Ward Work',                  'Ward Work'),
    ('Pharmacy Setup',             'Pharmacy Setup'),
    ('Lab Setup',                  'Lab Setup'),

    # ── LABOUR ──
    ('Labour Charges',             'Labour Charges'),
    ('Mason / Mistri',             'Mason / Mistri'),
    ('Building Worker Expense',    'Building Worker Expense'),
    ('Contractor Payment',         'Contractor Payment'),

    # ── SALARY & STAFF ──
    ('Salary - Security Guard',    'Salary - Security Guard'),
    ('Salary - Site Supervisor',   'Salary - Site Supervisor'),
    ('Salary - Other Staff',       'Salary - Other Staff'),

    # ── TRANSPORT & EQUIPMENT ──
    ('Transport / Vehicle',        'Transport / Vehicle'),
    ('Equipment Rental',           'Equipment Rental'),
    ('Generator / Power',          'Generator / Power'),
    ('Crane / JCB / Machinery',    'Crane / JCB / Machinery'),

    # ── OTHER ──
    ('Government Fee / NOC',       'Government Fee / NOC'),
    ('Architect / Engineer Fee',   'Architect / Engineer Fee'),
    ('Site Office Expense',        'Site Office Expense'),
    ('Petrol / Diesel',            'Petrol / Diesel'),
    ('Misc / Other',               'Misc / Other'),
]
AREA_CHOICES = [
    # ── EXCAVATION & FOUNDATION ──
    ('Soil Removal / Excavation', 'Soil Removal / Excavation'),
    ('Raft Foundation',           'Raft Foundation'),
    ('PCC Work',                  'PCC Work'),
    ('RCC Work',                  'RCC Work'),
    ('Basement',                  'Basement'),
    # ── FLOORS ──
    ('Ground Floor',    'Ground Floor'),
    ('First Floor',     'First Floor'),
    ('Second Floor',    'Second Floor'),
    ('Third Floor',     'Third Floor'),
    ('Fourth Floor',    'Fourth Floor'),
    ('Terrace',         'Terrace'),
    ('Staircase',       'Staircase'),
    # ── HOSPITAL AREAS ──
    ('Reception',       'Reception'),
    ('OPD',             'OPD'),
    ('OT',              'OT'),
    ('Labour Room',     'Labour Room'),
    ('Ward',            'Ward'),
    ('Private Room',    'Private Room'),
    ('ICU',             'ICU'),
    ('Pharmacy',        'Pharmacy'),
    ('Lab',             'Lab'),
    ('X-Ray',           'X-Ray'),
    ('Toilet',          'Toilet'),
    ('Parking',         'Parking'),
    ('Front Elevation', 'Front Elevation'),
    ('General Building','General Building'),
]

PAYMENT_MODE_CHOICES = [
    ('Cash', 'Cash'),
    ('UPI', 'UPI'),
    ('Bank Transfer', 'Bank Transfer'),
    ('Cheque', 'Cheque'),
    ('Credit', 'Credit'),
]

PAID_BY_CHOICES = [
    ('Dr. Pratap Senecha', 'Dr. Pratap Senecha'),
    ('Mr. Lumbaram',       'Mr. Lumbaram'),
    ('Mr. Poonaram',       'Mr. Poonaram'),
    ('Company',            'Company'),
    ('Site Supervisor',    'Site Supervisor'),
]

PAID_FROM_CHOICES = [
    ('Personal', 'Personal'),
    ('Company', 'Company'),
    ('Cash Box', 'Cash Box'),
    ('Bank', 'Bank'),
]

APPROVAL_STATUS_CHOICES = [
    ('Pending', 'Pending'),
    ('Approved', 'Approved'),
    ('Rejected', 'Rejected'),
]

APPROVED_BY_CHOICES = [
    ('Dr. Pratap Senecha', 'Dr. Pratap Senecha'),
    ('Mr. Lumbaram',       'Mr. Lumbaram'),
    ('Mr. Poonaram',       'Mr. Poonaram'),
    ('All 3',              'All 3'),
]

WORK_STATUS_CHOICES = [
    ('Done', 'Done'),
    ('Pending', 'Pending'),
    ('Partial', 'Partial'),
]

YES_NO_PARTIAL_CHOICES = [
    ('Yes', 'Yes'),
    ('No', 'No'),
    ('Partial', 'Partial'),
]

INVOICE_TYPE_CHOICES = [
    ('Tax Invoice', 'Tax Invoice'),
    ('Estimate', 'Estimate'),
    ('Cash Memo', 'Cash Memo'),
    ('Quotation', 'Quotation'),
    ('NA', 'NA'),
]

REIMBURSED_CHOICES = [
    ('Yes', 'Yes'),
    ('No', 'No'),
    ('Pending', 'Pending'),
]


# ===================== VENDOR =====================

class Vendor(models.Model):
    name       = models.CharField(max_length=200)
    mobile     = models.CharField(max_length=20, blank=True, null=True)
    work_type  = models.CharField(max_length=100, blank=True, null=True)
    gst_no     = models.CharField(max_length=50, blank=True, null=True)
    address    = models.TextField(blank=True, null=True)
    notes      = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


# ===================== CONSTRUCTION EXPENSE =====================

class ConstructionExpense(models.Model):
    expense_id = models.CharField(max_length=20, unique=True, blank=True)

    date         = models.DateField(default=timezone.now)
    expense_head = models.CharField(max_length=100, choices=EXPENSE_HEAD_CHOICES)
    subcategory  = models.CharField(max_length=200, blank=True, null=True)
    description  = models.TextField()

    area_location = models.CharField(max_length=100, choices=AREA_CHOICES, blank=True, null=True)

    vendor        = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True)
    vendor_mobile = models.CharField(max_length=20, blank=True, null=True)
    bill_no       = models.CharField(max_length=100, blank=True, null=True)

    qty  = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    unit = models.CharField(max_length=50, blank=True, null=True)
    rate = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)

    amount       = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gst_percent  = models.DecimalField(max_digits=5,  decimal_places=2, default=0)
    gst_amount   = models.DecimalField(max_digits=12, decimal_places=2, default=0, blank=True, null=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, blank=True, null=True)

    payment_mode = models.CharField(max_length=50, choices=PAYMENT_MODE_CHOICES, blank=True, null=True)
    paid_by      = models.CharField(max_length=50, choices=PAID_BY_CHOICES,      blank=True, null=True)
    paid_from    = models.CharField(max_length=50, choices=PAID_FROM_CHOICES,    blank=True, null=True)

    approval_status = models.CharField(max_length=20, choices=APPROVAL_STATUS_CHOICES, default='Pending')
    approved_by     = models.CharField(max_length=50, choices=APPROVED_BY_CHOICES, blank=True, null=True)

    work_status       = models.CharField(max_length=20, choices=WORK_STATUS_CHOICES,    blank=True, null=True)
    material_received = models.CharField(max_length=20, choices=YES_NO_PARTIAL_CHOICES, blank=True, null=True)

    invoice_type = models.CharField(max_length=50, choices=INVOICE_TYPE_CHOICES, blank=True, null=True)

    balance_due = models.DecimalField(max_digits=12, decimal_places=2, default=0, blank=True, null=True)
    due_date    = models.DateField(blank=True, null=True)

    remarks        = models.TextField(blank=True, null=True)
    bill_image     = models.ImageField(upload_to='construction_expenses/bills/',       blank=True, null=True)
    site_photo     = models.ImageField(upload_to='construction_expenses/site_photos/', blank=True, null=True)
    quotation_file = models.FileField(upload_to='construction_expenses/quotations/',   blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.expense_id:
            last_id = ConstructionExpense.objects.count() + 1
            self.expense_id = f"EXP-{last_id:04d}"
        if self.vendor and not self.vendor_mobile:
            self.vendor_mobile = self.vendor.mobile
        self.gst_amount   = (self.amount * self.gst_percent) / 100 if self.amount and self.gst_percent else 0
        self.total_amount = self.amount + self.gst_amount if self.amount else 0
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.expense_id} - {self.expense_head} - ₹{self.total_amount}"

    class Meta:
        ordering            = ['-created_at']
        verbose_name        = 'Construction Expense'
        verbose_name_plural = 'Construction Expenses'


# ===================== CONSTRUCTION MEDIA (PHOTOS, VIDEOS & DOCUMENTS) =====================

CONSTRUCTION_MEDIA_VIDEO_EXTENSIONS    = ['mp4', 'mov', 'avi', 'mkv', 'webm', '3gp']
CONSTRUCTION_MEDIA_PHOTO_EXTENSIONS    = ['jpg', 'jpeg', 'png', 'webp', 'heic']
CONSTRUCTION_MEDIA_DOCUMENT_EXTENSIONS = ['pdf', 'doc', 'docx', 'dwg', 'dxf']


def construction_media_upload_path(instance, filename):
    return f"construction_media/{timezone.now():%Y/%m}/{filename}"


class ConstructionMedia(models.Model):
    MEDIA_TYPE_CHOICES = [('video', 'Video'), ('photo', 'Photo'), ('document', 'Document')]

    file        = models.FileField(
        upload_to=construction_media_upload_path,
        validators=[FileExtensionValidator(
            allowed_extensions=(
                CONSTRUCTION_MEDIA_VIDEO_EXTENSIONS
                + CONSTRUCTION_MEDIA_PHOTO_EXTENSIONS
                + CONSTRUCTION_MEDIA_DOCUMENT_EXTENSIONS
            )
        )],
    )
    media_type  = models.CharField(max_length=10, choices=MEDIA_TYPE_CHOICES, blank=True)
    caption     = models.CharField(max_length=255, blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.media_type and self.file:
            ext = self.file.name.rsplit('.', 1)[-1].lower()
            if ext in CONSTRUCTION_MEDIA_PHOTO_EXTENSIONS:
                self.media_type = 'photo'
            elif ext in CONSTRUCTION_MEDIA_DOCUMENT_EXTENSIONS:
                self.media_type = 'document'
            else:
                self.media_type = 'video'
        super().save(*args, **kwargs)

    def __str__(self):
        return self.caption or f"Construction {self.get_media_type_display()} {self.pk}"

    @property
    def filename(self):
        return os.path.basename(self.file.name)

    _FILENAME_DATE_RE = re.compile(r'(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})')

    @property
    def display_date(self):
        """The real capture date embedded in imported WhatsApp filenames
        (e.g. '...VIDEO-2026-05-29-09-40-36.mov'), falling back to
        uploaded_at for files that don't carry that pattern."""
        match = self._FILENAME_DATE_RE.search(self.filename)
        if match:
            year, month, day, hour, minute, second = (int(g) for g in match.groups())
            try:
                naive = datetime(year, month, day, hour, minute, second)
                return timezone.make_aware(naive, timezone.get_current_timezone())
            except ValueError:
                pass
        return self.uploaded_at

    @property
    def file_size_display(self):
        try:
            size = self.file.size
        except (OSError, ValueError):
            return ""
        size = float(size)
        for unit in ('B', 'KB', 'MB', 'GB'):
            if size < 1024 or unit == 'GB':
                return f"{size:.0f} {unit}" if unit == 'B' else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"

    class Meta:
        ordering            = ['-uploaded_at']
        verbose_name        = 'Construction Media'
        verbose_name_plural = 'Construction Media'


# ===================== PARTNER PAYMENT =====================

class PartnerPayment(models.Model):
    date         = models.DateField(default=timezone.now)
    partner_name = models.CharField(max_length=50, choices=PAID_BY_CHOICES)
    amount_paid  = models.DecimalField(max_digits=12, decimal_places=2)
    paid_for     = models.CharField(max_length=255)
    mode         = models.CharField(max_length=50, choices=PAYMENT_MODE_CHOICES, blank=True, null=True)
    expense_ref  = models.ForeignKey(ConstructionExpense, on_delete=models.SET_NULL, blank=True, null=True)
    reimbursed   = models.CharField(max_length=20, choices=REIMBURSED_CHOICES, default='No')
    remarks      = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.partner_name} - ₹{self.amount_paid}"

    class Meta:
        ordering = ['-date']


# ===================== EXPENSE BUDGET =====================

class ExpenseBudget(models.Model):
    expense_head  = models.CharField(max_length=100, choices=EXPENSE_HEAD_CHOICES, unique=True)
    budget_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def actual_spent(self):
        return ConstructionExpense.objects.filter(
            expense_head=self.expense_head
        ).aggregate(total=models.Sum('total_amount'))['total'] or 0

    def difference(self):
        return self.budget_amount - self.actual_spent()

    def status(self):
        return "Within Budget" if self.difference() >= 0 else "Over Budget"

    def __str__(self):
        return f"{self.expense_head} - Budget ₹{self.budget_amount}"

    class Meta:
        verbose_name        = 'Expense Budget'
        verbose_name_plural = 'Expense Budgets'

        # =====================================================================
# USG REPORT MODEL
# =====================================================================

class USGReport(models.Model):
    """
    USG (Ultrasonography) Report. Findings are captured as one editable
    narrative paragraph (pre-filled from a per-scan-type standard template)
    plus a separate Impression, mirroring how the report is actually
    dictated and printed. Linked to a Patient and optionally to a
    Consultation / InvestigationBillItem.
    """

    # ── SCAN TYPES ────────────────────────────────────────────────────
    SCAN_TYPE_CHOICES = [
        ("ABDOMEN",             "Abdomen"),
        ("PELVIS",              "Pelvis"),
        ("ABDOMEN_PELVIS",      "Abdomen & Pelvis"),
        ("OBSTETRIC",           "Obstetric (Pregnancy)"),
        ("KUB",                 "KUB (Kidney-Ureter-Bladder)"),
        ("THYROID",             "Thyroid"),
        ("BREAST",              "Breast"),
        ("SCROTUM",             "Scrotum"),
        ("NECK",                "Neck / Soft Tissue"),
        ("LIVER_PORTAL_DOPPLER","Liver & Portal Doppler"),
        ("WHOLE_ABDOMEN",       "Whole Abdomen"),
        ("GUIDED_ASPIRATION",   "USG-Guided Aspiration"),
        ("OTHER",               "Other"),
    ]

    # ── REPORT FINDING STATUS ─────────────────────────────────────────
    IMPRESSION_STATUS_CHOICES = [
        ("NORMAL",   "Normal Study"),
        ("ABNORMAL", "Abnormal / Significant Findings"),
        ("INCONCLUSIVE", "Inconclusive / Follow-up Advised"),
    ]

    # Standard normal-study narrative per scan type — the doctor's own
    # wording, used to prefill the findings box on a new report of that
    # scan type. Scan types not listed here just start with an empty
    # findings box until a standard template is supplied for them.
    _ABDOMEN_PELVIS_COMMON = """Liver: The liver is normal in size measuring __ cm. The echotexture is normal. No focal hepatic lesion is seen. The intrahepatic ducts are not dilated. The portal vein and common bile duct show normal calibre.
Portal Vein: Measuring __ mm.

Gallbladder: The gallbladder is distended and shows smooth walls. No gallstones or biliary sludge is seen. The wall thickness is within normal limits. No evidence of pericholecystic fluid.
CBD: Measuring __ size normal.

Pancreas: The pancreas is normal in size and echotexture. The pancreatic duct is not dilated.
Spleen: The spleen is normal in size, measuring __ cm. No splenic lesion is seen.

Kidneys: Both kidneys are normal in size, shape and position and show normal cortico-medullary differentiation.
Right kidney measures __
Left kidney measures __

Bladder: The urinary bladder is adequately filled. Its wall is not thickened. No evidence of diverticulum or calculus.

{PELVIC_ORGANS}

Colon wall thickness __ mm. Ileal wall thickness __ mm."""

    _PELVIC_ORGANS_FEMALE = "Uterus and Ovaries: The uterus is __ size, cm, anteverted shape, homogenous echotexture, myometrium and endometrial thickness __ mm, and ovaries are of normal size."
    _PELVIC_ORGANS_MALE = "Prostate: The prostate gland is normal in size and shows homogenous echotexture. No focal lesion is seen. Post-void residual urine is minimal."

    # Standard normal-study narrative per scan type — the doctor's own
    # wording, used to prefill the findings box on a new report of that
    # scan type. A value may be a plain string (same for every patient)
    # or a {"male": ..., "female": ..., "default": ...} dict for scan
    # types whose pelvic-organ paragraph depends on the patient's sex.
    # Scan types not listed here just start with an empty findings box.
    FINDINGS_TEMPLATES = {
        "ABDOMEN_PELVIS": {
            "male":    _ABDOMEN_PELVIS_COMMON.replace("{PELVIC_ORGANS}", _PELVIC_ORGANS_MALE),
            "female":  _ABDOMEN_PELVIS_COMMON.replace("{PELVIC_ORGANS}", _PELVIC_ORGANS_FEMALE),
            "default": _ABDOMEN_PELVIS_COMMON.replace("{PELVIC_ORGANS}", _PELVIC_ORGANS_FEMALE),
        },
    }

    @classmethod
    def default_findings_text(cls, scan_type, gender=None):
        template = cls.FINDINGS_TEMPLATES.get(scan_type, "")
        if isinstance(template, dict):
            key = "male" if gender == "Male" else "female" if gender == "Female" else "default"
            return template.get(key, template.get("default", ""))
        return template

    # ── CORE LINKS ────────────────────────────────────────────────────
    patient      = models.ForeignKey(
        "Patient", on_delete=models.CASCADE, related_name="usg_reports"
    )
    consultation = models.ForeignKey(
        "Consultation", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="usg_reports"
    )
    bill_item    = models.ForeignKey(
        "InvestigationBillItem", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="usg_reports",
        help_text="Lab bill item that triggered this USG"
    )

    # ── REPORT IDENTITY ────────────────────────────────────────────────
    report_no    = models.CharField(max_length=20, unique=True, blank=True,
                                    help_text="Auto-generated e.g. USG-000123")
    scan_type    = models.CharField(max_length=50, choices=SCAN_TYPE_CHOICES,
                                    default="ABDOMEN_PELVIS")
    report_date  = models.DateField(default=timezone.now)
    report_time  = models.TimeField(null=True, blank=True)

    # ── REFERRAL ───────────────────────────────────────────────────────
    referred_by  = models.ForeignKey(
        "Doctor", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="usg_referrals"
    )
    clinical_indication = models.TextField(blank=True,
        help_text="Reason / clinical indication for the scan")

    # ── MACHINE / TECH ─────────────────────────────────────────────────
    machine_used   = models.CharField(max_length=100, blank=True,
                                      help_text="e.g. Philips Affinity 50G")
    probe_used     = models.CharField(max_length=100, blank=True,
                                      help_text="e.g. Curvilinear 3.5 MHz")
    sonographer    = models.CharField(max_length=120, blank=True)

    # ── FINDINGS (narrative) ──────────────────────────────────────────
    findings_text  = models.TextField(blank=True, default="",
        help_text="Organ-wise findings, pre-filled from the standard "
                   "template for the selected scan type and edited per case")

    # ── IMPRESSION / CONCLUSION ───────────────────────────────────────
    impression_status  = models.CharField(
        max_length=20, choices=IMPRESSION_STATUS_CHOICES, default="NORMAL"
    )
    impression         = models.TextField(
        help_text="Final impression / diagnosis summary"
    )
    advice             = models.TextField(blank=True,
        help_text="Follow-up / correlation advice")

    # ── REPORTING DOCTOR ─────────────────────────────────────────────
    reporting_doctor   = models.ForeignKey(
        "Doctor", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="usg_reports_signed"
    )
    is_verified        = models.BooleanField(default=False,
        help_text="Tick when radiologist has verified the report")

    # ── METADATA ─────────────────────────────────────────────────────
    created_by         = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL,
        null=True, blank=True
    )
    created_at         = models.DateTimeField(auto_now_add=True)
    updated_at         = models.DateTimeField(auto_now=True)

    class Meta:
        ordering            = ["-report_date", "-created_at"]
        verbose_name        = "USG Report"
        verbose_name_plural = "USG Reports"

    def save(self, *args, **kwargs):
        if not self.report_no:
            last = USGReport.objects.order_by("id").last()
            num  = (last.id + 1) if last else 1
            self.report_no = f"USG-{num:06d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.report_no} | {self.patient.full_name} | {self.get_scan_type_display()}"

    # ===================== PRESCRIPTION TEMPLATE =====================
class PrescriptionTemplate(models.Model):
    name       = models.CharField(max_length=100, unique=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.name

class PrescriptionTemplateItem(models.Model):
    template     = models.ForeignKey(PrescriptionTemplate, on_delete=models.CASCADE, related_name='items')
    medicine     = models.CharField(max_length=150)
    dose         = models.CharField(max_length=50,  blank=True)
    frequency    = models.CharField(max_length=50,  blank=True)
    duration     = models.CharField(max_length=50,  blank=True)
    instructions = models.CharField(max_length=100, blank=True)
    order        = models.PositiveSmallIntegerField(default=0)
    class Meta: ordering = ['order']

class VillageMaster(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class DrugMaster(models.Model):
    name         = models.CharField(max_length=150)
    generic_name = models.CharField(max_length=150, blank=True, default="")
    strength     = models.CharField(max_length=50,  blank=True, default="")
    category     = models.CharField(max_length=100, blank=True, default="")
    atc_code     = models.CharField(max_length=10, blank=True, default="",
                       validators=[atc_code_validator],
                       help_text="WHO ATC code e.g. 'N02BE01' for Paracetamol")
    is_active    = models.BooleanField(default=True)
    sort_order   = models.IntegerField(default=99)
    default_dose         = models.CharField(max_length=50,  blank=True, default="")
    default_frequency    = models.CharField(max_length=50,  blank=True, default="")
    default_duration     = models.CharField(max_length=50,  blank=True, default="")
    default_instructions = models.CharField(max_length=100, blank=True, default="")
    def __str__(self): return self.name


class Partner(models.Model):
    name = models.CharField(max_length=100)
    share_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    def __str__(self):
        return self.name


class PartnerDeposit(models.Model):
    TRANSACTION_TYPE = [
        ('deposit', 'Deposit'),
        ('withdraw', 'Withdraw'),
    ]
    partner = models.ForeignKey(Partner, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPE, default='deposit')
    date = models.DateField()
    note = models.CharField(max_length=200, blank=True)
    voucher_no = models.CharField(max_length=50, unique=True, blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    added_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.partner.name} Rs {self.amount} ({self.transaction_type}) on {self.date}"

# ======================================================
# IPD PATIENT LOGS AND METRIC HISTORIES
# ======================================================

class IPDSymptomHistory(models.Model):
    """
    Logs historical snapshot captures of selected symptom combinations.
    Keeps historical records safe from master state overwrites.
    """
    # Relates securely back to your primary IPD admission records table
    admission = models.ForeignKey(
        'IPDAdmission', 
        on_delete=models.CASCADE, 
        related_name="symptom_history"
    )
    
    # Stores comma-delimited strings parsed from operational template matrix lists
    symptoms = models.TextField()
    
    # Records server timestamp benchmarks dynamically upon user click events
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at"]
        verbose_name = "IPD Symptom Log"
        verbose_name_plural = "IPD Symptom History Records"

    def __str__(self):
        return f"{self.admission.patient.full_name} — {self.recorded_at.strftime('%b %d, %Y %H:%M')}"


# ======================================================
# IPD TREATMENT PLAN HISTORY
# ======================================================

class IPDTreatmentHistory(models.Model):
    """
    Logs each treatment plan entry saved for an admission, so past entries
    remain visible instead of being overwritten.
    """
    admission = models.ForeignKey(
        'IPDAdmission',
        on_delete=models.CASCADE,
        related_name="treatment_history"
    )
    treatment_plan = models.TextField()
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at"]


# ======================================================
# IPD PROCEDURE
# ======================================================

class IPDProcedure(models.Model):
    """
    A structured record of a procedure performed during an IPD admission —
    the primary source for the Discharge tab's "Procedure Performed" field
    and, through it, the Course in Hospital narrative (falls back to the
    Treatment tab's free text when no structured entry exists yet).
    """
    ANAESTHESIA_CHOICES = [
        ("General", "General"),
        ("Spinal", "Spinal"),
        ("Local", "Local"),
        ("Regional", "Regional"),
        ("Sedation", "Sedation"),
    ]

    admission = models.ForeignKey(
        'IPDAdmission',
        on_delete=models.CASCADE,
        related_name="procedures"
    )
    procedure_name   = models.CharField(max_length=255)
    anaesthesia_type = models.CharField(max_length=20, choices=ANAESTHESIA_CHOICES)
    procedure_date   = models.DateField()
    recorded_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-procedure_date", "-recorded_at"]

    def __str__(self):
        return f"{self.procedure_name} - {self.admission.ipd_no}"
        verbose_name = "IPD Treatment Log"
        verbose_name_plural = "IPD Treatment History Records"

    def __str__(self):
        return f"{self.admission.patient.full_name} — {self.recorded_at.strftime('%b %d, %Y %H:%M')}"


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
        skipped = f", {self.skipped_count} skipped -- no match" if self.skipped_count else ""
        return f"{self.updated_count} updated, {self.created_count} new{skipped}"


class TPAImportRow(models.Model):
    """Per-row audit detail for a TPAImportBatch -- what matched, what changed."""
    ACTION_CHOICES = [
        ("updated", "Updated existing record"),
        ("created", "Created new draft record"),
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


auditlog.register(TPAPatient)


# ======================================================
# USG IMPRESSION OPTIONS -- quick-select chips for the
# Impression field, grouped like the ICD code list
# (category + sort_order, both editable from the admin panel).
# ======================================================

class USGImpressionOption(models.Model):
    CATEGORY_CHOICES = [
        ("liver_gallbladder",      "1. Liver and Gall Bladder"),
        ("kidney",                 "2. Kidney"),
        ("ureter_bladder_prostate", "3. Ureter, Bladder and Prostate"),
        ("uterus_ovary",           "4. Uterus and Ovary"),
        ("misc",                   "5. Miscellaneous"),
    ]

    text = models.CharField(max_length=255)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default="misc")
    sort_order = models.IntegerField(default=9999)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["category", "sort_order", "text"]
        verbose_name = "USG Impression Option"
        verbose_name_plural = "USG Impression Options"

    def __str__(self):
        return self.text
