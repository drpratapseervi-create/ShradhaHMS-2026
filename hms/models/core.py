from django.db import models
from django.core.validators import RegexValidator
from django.utils import timezone
from datetime import date
from encrypted_model_fields.fields import EncryptedCharField

# WHO ATC codes always start with a letter (e.g. 'N02BE01'); drug strength
# values like "250+10mg" start with a digit — this catches that mix-up.
atc_code_validator = RegexValidator(
    regex=r'^[A-Za-z][A-Za-z0-9]*$',
    message="Enter a valid ATC code (e.g. 'N02BE01'), not a drug strength.",
)
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
    is_surgeon = models.BooleanField(
        default=True, help_text="Show this person in the OT 'Surgeon' dropdown"
    )
    is_assistant = models.BooleanField(
        default=True, help_text="Show this person in the OT 'Assistant' dropdown"
    )
    is_anesthetist = models.BooleanField(
        default=True, help_text="Show this person in the OT 'Anesthetist' dropdown"
    )

    def __str__(self):
        if self.department:
            return f"{self.full_name} ({self.department.name})"
        return self.full_name

