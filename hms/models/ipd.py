from django.db import models
from django.utils import timezone
from .core import Doctor

# ===================== WARD & BED =====================
class Ward(models.Model):
    name       = models.CharField(max_length=100)
    total_beds = models.IntegerField()
    bed_charge_item = models.ForeignKey(
        "BillItem", on_delete=models.SET_NULL, null=True, blank=True, related_name="wards",
        help_text="Per-day bed charge billed for a stay in this ward",
    )

    def __str__(self):
        return self.name


class Bed(models.Model):
    HOUSEKEEPING_CHOICES = [
        ("",         "Ready"),
        ("CLEANING", "Cleaning"),
        ("BLOCKED",  "Blocked (maintenance)"),
    ]

    ward       = models.ForeignKey(Ward, on_delete=models.CASCADE)
    bed_number = models.CharField(max_length=10)
    is_occupied = models.BooleanField(default=False)
    housekeeping = models.CharField(max_length=10, choices=HOUSEKEEPING_CHOICES, blank=True, default="")

    def __str__(self):
        return f"{self.ward.name} - Bed {self.bed_number}"

    @property
    def is_available(self):
        return not self.is_occupied and not self.housekeeping


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

    discharge_message_sent_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When the WhatsApp discharge thank-you message was sent -- unset means not yet sent.",
    )
    followup_reminder_sent_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When the WhatsApp follow-up-date reminder was sent -- unset means not yet sent.",
    )

    # -------- ATTENDANT --------
    attendant_name     = models.CharField(max_length=100, blank=True)
    attendant_relation = models.CharField(max_length=50, blank=True)
    attendant_mobile   = models.CharField(max_length=15, blank=True)

    # -------- STATUS --------
    status = models.CharField(
        max_length=20,
        choices=[
            ("ADMITTED",   "Admitted"),
            ("DISCHARGED", "Discharged"),
            ("CANCELLED",  "Cancelled (entered in error)"),
        ],
        default="ADMITTED"
    )
    # Set when an admin discharges with the bill still unpaid.
    discharge_override_reason = models.CharField(max_length=200, blank=True)
    discharged_by = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.ipd_no:
            last = IPDAdmission.objects.exclude(ipd_no__isnull=True).order_by("id").last()
            number = (int(last.ipd_no.split("-")[-1]) + 1) if last and last.ipd_no else 1
            self.ipd_no = f"IPD-{number:05d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.ipd_no} - {self.patient.full_name}"


# ===================== BED STAY =====================
class BedStay(models.Model):
    """One continuous stay in one bed. A transfer ends one stay and starts the next."""
    admission = models.ForeignKey(IPDAdmission, on_delete=models.CASCADE, related_name="bed_stays")
    bed       = models.ForeignKey(Bed, on_delete=models.PROTECT, related_name="stays")
    ward      = models.ForeignKey(Ward, on_delete=models.PROTECT, related_name="stays")
    start     = models.DateTimeField()
    end       = models.DateTimeField(null=True, blank=True)  # null while current

    class Meta:
        ordering = ["start", "id"]

    def __str__(self):
        return f"{self.admission.ipd_no} in {self.bed} from {self.start:%d %b %H:%M}"


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


