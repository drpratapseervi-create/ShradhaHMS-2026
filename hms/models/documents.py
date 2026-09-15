from django.db import models
from django.utils import timezone
from datetime import timedelta

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

