from encrypted_model_fields.fields import EncryptedCharField
from auditlog.registry import auditlog
from django.db import models
from django.core.validators import RegexValidator
from django.utils import timezone
from datetime import date, timedelta
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

    # ===== CLINICAL =====
    chief_complaints = models.TextField(blank=True)
    examination      = models.TextField(blank=True)
    procedures_performed = models.TextField(blank=True)
    symptoms         = models.ManyToManyField("Symptom", blank=True)
    signs            = models.ManyToManyField("Sign", blank=True)
    past_history     = models.ManyToManyField("PastHistory", blank=True)
    surgical_history  = models.ManyToManyField("SurgicalHistory", blank=True)
    surgery_date     = models.DateField(null=True, blank=True)
    diagnosis_text   = models.CharField(max_length=255, blank=True)
    diagnosis_icd    = models.ForeignKey(
        ICDCode, on_delete=models.SET_NULL, null=True, blank=True
    )
    icd_codes        = models.ManyToManyField(ICDCode, blank=True, related_name='consultations')
    ai_notes = models.TextField(blank=True, null=True)

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

    class Meta:
        ordering = ["category__dept_code", "name"]

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

    def __str__(self):
        return self.name


# ===================== SIGN =====================
class Sign(models.Model):
    name       = models.CharField(max_length=200)
    department = models.ForeignKey(
        Department, on_delete=models.CASCADE, related_name="signs"
    )
    is_active = models.BooleanField(default=True)

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
# USG REPORT MODEL — add this block to models.py
# =====================================================================

class USGReport(models.Model):
    """
    Auto-generated USG (Ultrasonography) Report.
    Linked to a Patient and optionally to a Consultation / InvestigationBillItem.
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

    # ══════════════════════════════════════════════════════════════════
    # ORGAN-WISE FINDINGS  (blank = not examined / normal)
    # ══════════════════════════════════════════════════════════════════

    # ── LIVER ─────────────────────────────────────────────────────────
    liver_size         = models.CharField(max_length=100, blank=True,
                                          help_text="e.g. 14.2 cm")
    liver_echotexture  = models.CharField(max_length=200, blank=True,
                                          help_text="e.g. Normal homogeneous")
    liver_lesion       = models.TextField(blank=True,
                                          help_text="Any focal lesion description")
    liver_notes        = models.TextField(blank=True)

    # ── GALLBLADDER ───────────────────────────────────────────────────
    gb_size            = models.CharField(max_length=100, blank=True)
    gb_wall_thickness  = models.CharField(max_length=50, blank=True,
                                          help_text="e.g. 3 mm")
    gb_calculi         = models.BooleanField(default=False,
                                             verbose_name="Gallbladder Calculi")
    gb_calculi_size    = models.CharField(max_length=100, blank=True,
                                          help_text="e.g. 8mm calculus in neck")
    gb_notes           = models.TextField(blank=True)

    # ── CBD ───────────────────────────────────────────────────────────
    cbd_diameter       = models.CharField(max_length=50, blank=True,
                                          help_text="e.g. 4 mm — normal <6mm")
    cbd_notes          = models.TextField(blank=True)

    # ── SPLEEN ────────────────────────────────────────────────────────
    spleen_size        = models.CharField(max_length=100, blank=True,
                                          help_text="e.g. 10.5 cm")
    spleen_notes       = models.TextField(blank=True)

    # ── PANCREAS ──────────────────────────────────────────────────────
    pancreas_notes     = models.TextField(blank=True,
                                          help_text="e.g. Normal in size and echotexture")

    # ── KIDNEYS ───────────────────────────────────────────────────────
    rt_kidney_size     = models.CharField(max_length=100, blank=True,
                                          help_text="e.g. 10.2 × 4.5 cm")
    rt_kidney_notes    = models.TextField(blank=True)
    lt_kidney_size     = models.CharField(max_length=100, blank=True)
    lt_kidney_notes    = models.TextField(blank=True)
    kidney_calculi     = models.BooleanField(default=False)
    kidney_calculi_detail = models.TextField(blank=True)
    hydronephrosis     = models.BooleanField(default=False)
    hydronephrosis_detail = models.TextField(blank=True)

    # ── URINARY BLADDER ───────────────────────────────────────────────
    bladder_notes      = models.TextField(blank=True,
                                          help_text="e.g. Well distended, smooth walls")
    post_void_residue  = models.CharField(max_length=50, blank=True,
                                          help_text="PVR in ml")

    # ── UTERUS / GYN (Female) ─────────────────────────────────────────
    uterus_size        = models.CharField(max_length=150, blank=True,
                                          help_text="e.g. 7.5 × 4.2 × 3.8 cm")
    uterus_position    = models.CharField(max_length=50, blank=True,
                                          help_text="e.g. Anteverted / Retroverted")
    uterus_echotexture = models.CharField(max_length=200, blank=True)
    endometrial_thickness = models.CharField(max_length=50, blank=True,
                                              help_text="e.g. 8 mm")
    uterus_notes       = models.TextField(blank=True)

    # ── OVARIES ───────────────────────────────────────────────────────
    rt_ovary_size      = models.CharField(max_length=150, blank=True,
                                          help_text="e.g. 3.0 × 2.0 × 1.5 cm")
    rt_ovary_notes     = models.TextField(blank=True)
    lt_ovary_size      = models.CharField(max_length=150, blank=True)
    lt_ovary_notes     = models.TextField(blank=True)
    adnexal_notes      = models.TextField(blank=True)

    # ── OBSTETRIC ─────────────────────────────────────────────────────
    lmp                = models.DateField(null=True, blank=True,
                                          verbose_name="LMP (Last Menstrual Period)")
    ga_by_lmp          = models.CharField(max_length=50, blank=True,
                                          verbose_name="GA by LMP",
                                          help_text="e.g. 28 weeks 3 days")
    ga_by_scan         = models.CharField(max_length=50, blank=True,
                                          verbose_name="GA by Scan")
    edd_by_lmp         = models.DateField(null=True, blank=True,
                                          verbose_name="EDD by LMP")
    edd_by_scan        = models.DateField(null=True, blank=True,
                                          verbose_name="EDD by Scan")
    fetal_presentation = models.CharField(max_length=100, blank=True,
                                          help_text="e.g. Cephalic / Breech")
    fetal_heart_rate   = models.CharField(max_length=50, blank=True,
                                          help_text="e.g. 148 bpm — regular")
    placental_location = models.CharField(max_length=200, blank=True)
    liquor             = models.CharField(max_length=100, blank=True,
                                          help_text="e.g. Adequate / Reduced")
    afi                = models.CharField(max_length=50, blank=True,
                                          verbose_name="AFI (cm)")
    biometry_bpd       = models.CharField(max_length=50, blank=True, verbose_name="BPD")
    biometry_hc        = models.CharField(max_length=50, blank=True, verbose_name="HC")
    biometry_ac        = models.CharField(max_length=50, blank=True, verbose_name="AC")
    biometry_fl        = models.CharField(max_length=50, blank=True, verbose_name="FL")
    efw                = models.CharField(max_length=100, blank=True,
                                          verbose_name="Estimated Fetal Weight")
    obstetric_notes    = models.TextField(blank=True)

    # ── PROSTATE (Male) ───────────────────────────────────────────────
    prostate_size      = models.CharField(max_length=150, blank=True,
                                          help_text="e.g. 3.5 × 3.0 × 3.2 cm, Vol 17 ml")
    prostate_notes     = models.TextField(blank=True)

    # ── THYROID / NECK ────────────────────────────────────────────────
    thyroid_rt         = models.CharField(max_length=200, blank=True)
    thyroid_lt         = models.CharField(max_length=200, blank=True)
    thyroid_isthmus    = models.CharField(max_length=100, blank=True)
    thyroid_notes      = models.TextField(blank=True)

    # ── BREAST ────────────────────────────────────────────────────────
    breast_rt          = models.TextField(blank=True)
    breast_lt          = models.TextField(blank=True)
    breast_notes       = models.TextField(blank=True)

    # ── ASCITES / FREE FLUID ──────────────────────────────────────────
    ascites            = models.BooleanField(default=False)
    ascites_detail     = models.TextField(blank=True)

    # ── FREE TEXT FINDINGS ────────────────────────────────────────────
    additional_findings = models.TextField(blank=True,
        help_text="Any other findings not captured above")

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

 # =====================================================================
# ADD THESE FIELDS TO YOUR EXISTING USGReport MODEL in models.py
# Paste inside the USGReport class, after the existing fields
# =====================================================================

    # ── LIVER (extended) ─────────────────────────────────────────────
    liver_focal_lesion      = models.BooleanField(default=False)
    liver_cyst              = models.BooleanField(default=False)
    liver_mass              = models.BooleanField(default=False)
    liver_ihbr_dilated      = models.BooleanField(default=False, verbose_name="IHBR Dilated")

    # ── GALLBLADDER (extended) ────────────────────────────────────────
    gb_calculi_present      = models.BooleanField(default=False)
    gb_calculi_detail       = models.CharField(max_length=200, blank=True)
    gb_wall_thick           = models.BooleanField(default=False)
    gb_distended            = models.BooleanField(default=False)
    gb_contracted           = models.BooleanField(default=False)
    gb_sludge               = models.BooleanField(default=False)
    gb_pericholecystic_fluid= models.BooleanField(default=False)
    gb_probe_tenderness     = models.BooleanField(default=False)

    # ── CBD (extended) ────────────────────────────────────────────────
    cbd_dilated             = models.BooleanField(default=False)

    # ── RIGHT KIDNEY ─────────────────────────────────────────────────
    rk_size                 = models.CharField(max_length=100, blank=True)
    rk_stone_present        = models.BooleanField(default=False)
    rk_stone_size           = models.CharField(max_length=100, blank=True)
    rk_stone_site           = models.CharField(max_length=200, blank=True)
    rk_mild_hydronephrosis  = models.BooleanField(default=False)
    rk_moderate_hydronephrosis = models.BooleanField(default=False)
    rk_severe_hydronephrosis= models.BooleanField(default=False)
    rk_hydroureter          = models.BooleanField(default=False)
    rk_hydroureteronephrosis= models.BooleanField(default=False)
    rk_cyst_present         = models.BooleanField(default=False)
    rk_cyst_size            = models.CharField(max_length=100, blank=True)
    rk_cyst_location        = models.CharField(max_length=100, blank=True)
    rk_cyst_type            = models.CharField(max_length=100, blank=True, help_text="e.g. Simple / Complex")

    # ── LEFT KIDNEY ──────────────────────────────────────────────────
    lk_size                 = models.CharField(max_length=100, blank=True)
    lk_stone_present        = models.BooleanField(default=False)
    lk_stone_size           = models.CharField(max_length=100, blank=True)
    lk_stone_site           = models.CharField(max_length=200, blank=True)
    lk_mild_hydronephrosis  = models.BooleanField(default=False)
    lk_moderate_hydronephrosis = models.BooleanField(default=False)
    lk_severe_hydronephrosis= models.BooleanField(default=False)
    lk_hydroureter          = models.BooleanField(default=False)
    lk_hydroureteronephrosis= models.BooleanField(default=False)
    lk_cyst_present         = models.BooleanField(default=False)
    lk_cyst_size            = models.CharField(max_length=100, blank=True)
    lk_cyst_location        = models.CharField(max_length=100, blank=True)
    lk_cyst_type            = models.CharField(max_length=100, blank=True)

    # ── URETERIC CALCULUS ─────────────────────────────────────────────
    ureteric_side           = models.CharField(max_length=20, blank=True, help_text="Right / Left / Bilateral")
    ureteric_size           = models.CharField(max_length=100, blank=True)
    ureteric_site           = models.CharField(max_length=200, blank=True, help_text="e.g. VUJ / PUJ / mid-ureter")
    ureteric_hydroureter    = models.BooleanField(default=False)
    ureteric_hydronephrosis = models.BooleanField(default=False)
    ureteric_hydroureteronephrosis = models.BooleanField(default=False)

    # ── SPLEEN (extended) ─────────────────────────────────────────────
    splenomegaly            = models.BooleanField(default=False)
    spleen_cyst             = models.BooleanField(default=False)
    spleen_lesion           = models.BooleanField(default=False)

    # ── BLADDER (extended) ────────────────────────────────────────────
    bladder_state           = models.CharField(max_length=50, blank=True, help_text="e.g. Well distended / Partially filled / Empty")
    bladder_wall_thick      = models.BooleanField(default=False)
    bladder_internal_echoes = models.BooleanField(default=False)
    bladder_calculus        = models.BooleanField(default=False)
    bladder_mass            = models.BooleanField(default=False)
    pvrv                    = models.CharField(max_length=50, blank=True, verbose_name="Post-Void Residual Volume (ml)")

    # ── PROSTATE (extended) ───────────────────────────────────────────
    prostate_volume         = models.CharField(max_length=50, blank=True, help_text="Volume in cc/ml")
    prostate_echotexture    = models.CharField(max_length=200, blank=True)
    prostate_median_lobe    = models.BooleanField(default=False, help_text="Median lobe hypertrophy")
    prostatomegaly          = models.BooleanField(default=False)

    # ── UTERUS (extended) ─────────────────────────────────────────────
    uterus_myometrium       = models.CharField(max_length=200, blank=True, help_text="e.g. Homogeneous / Heterogeneous")
    pid_changes             = models.BooleanField(default=False, verbose_name="PID Changes")
    fibroid_present         = models.BooleanField(default=False)
    fibroid_size            = models.CharField(max_length=100, blank=True)
    fibroid_site            = models.CharField(max_length=100, blank=True, help_text="e.g. Anterior / Posterior / Fundal")
    fibroid_type            = models.CharField(max_length=100, blank=True, help_text="e.g. Intramural / Subserosal / Submucosal")

    # ── RIGHT OVARY ───────────────────────────────────────────────────
    ro_size                 = models.CharField(max_length=100, blank=True)
    ro_volume               = models.CharField(max_length=50, blank=True, help_text="Volume in cc")
    ro_bulky                = models.BooleanField(default=False)
    ro_cyst_present         = models.BooleanField(default=False)
    ro_cyst_size            = models.CharField(max_length=100, blank=True)
    ro_cyst_type            = models.CharField(max_length=100, blank=True, help_text="e.g. Simple / Hemorrhagic / Dermoid / Endometrioma")

    # ── LEFT OVARY ────────────────────────────────────────────────────
    lo_size                 = models.CharField(max_length=100, blank=True)
    lo_volume               = models.CharField(max_length=50, blank=True)
    lo_bulky                = models.BooleanField(default=False)
    lo_cyst_present         = models.BooleanField(default=False)
    lo_cyst_size            = models.CharField(max_length=100, blank=True)
    lo_cyst_type            = models.CharField(max_length=100, blank=True)

    # ── HERNIA ────────────────────────────────────────────────────────
    hernia_type             = models.CharField(max_length=100, blank=True, help_text="e.g. Inguinal / Umbilical / Incisional / Femoral")
    hernia_side             = models.CharField(max_length=20, blank=True, help_text="Right / Left / Bilateral")
    hernia_defect_size      = models.CharField(max_length=100, blank=True)
    hernia_reducible        = models.BooleanField(default=False)
    hernia_irreducible      = models.BooleanField(default=False)
    hernia_bowel_loops      = models.BooleanField(default=False)
    hernia_omentum          = models.BooleanField(default=False)
    hernia_cough_impulse    = models.BooleanField(default=False)

    # ── APPENDIX ──────────────────────────────────────────────────────
    appendix_visualized     = models.BooleanField(default=False)
    appendix_diameter       = models.CharField(max_length=50, blank=True, help_text="mm")
    appendix_noncompressible= models.BooleanField(default=False)
    appendix_probe_tenderness = models.BooleanField(default=False)
    appendix_periappendiceal_fluid = models.BooleanField(default=False)
    appendicolith           = models.BooleanField(default=False)
    inflamed_fat            = models.BooleanField(default=False, verbose_name="Inflamed Periappendiceal Fat")

    # ── BOWEL ─────────────────────────────────────────────────────────
    colitis_present         = models.BooleanField(default=False)
    colitis_site            = models.CharField(max_length=200, blank=True)
    sbo_present             = models.BooleanField(default=False, verbose_name="Small Bowel Obstruction")
    dilated_bowel_loops     = models.BooleanField(default=False)
    to_and_fro_peristalsis  = models.BooleanField(default=False)
    collapsed_distal_bowel  = models.BooleanField(default=False)
    gaseous_bowel_loops     = models.BooleanField(default=False)
    ibs_suggestion          = models.BooleanField(default=False, verbose_name="IBS Suggestion")

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
        verbose_name = "IPD Treatment Log"
        verbose_name_plural = "IPD Treatment History Records"

    def __str__(self):
        return f"{self.admission.patient.full_name} — {self.recorded_at.strftime('%b %d, %Y %H:%M')}"
