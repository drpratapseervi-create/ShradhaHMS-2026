from django.db import models
from django.utils import timezone

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
    # Named __TOKEN__ placeholders (instead of a bare "__") for the
    # measurements the "Measurements" panel on the report form fills in —
    # each is looked up by name in the JS, so it can target the right blank
    # regardless of where it falls in the paragraph. Kept human-readable
    # (still reads as an obvious fill-in-the-blank if edited by hand without
    # the panel) and always followed by its unit so the doctor never has to
    # guess cm vs mm while typing.
    _ABDOMEN_PELVIS_COMMON = """Liver: The liver is normal in size measuring __LIVER__ cm. The echotexture is normal. No focal hepatic lesion is seen. The intrahepatic ducts are not dilated. The portal vein and common bile duct show normal calibre.
Portal Vein: Measuring __PORTAL_VEIN__ mm.

Gallbladder: The gallbladder is distended and shows smooth walls. No gallstones or biliary sludge is seen. The wall thickness is within normal limits. No evidence of pericholecystic fluid.
CBD: Measuring __CBD__ mm, size normal.

Pancreas: The pancreas is normal in size and echotexture. The pancreatic duct is not dilated.
Spleen: The spleen is normal in size, measuring __SPLEEN__ cm. No splenic lesion is seen.

Kidneys: Both kidneys are normal in size, shape and position and show normal cortico-medullary differentiation.
Right Kidney: measures __RIGHT_KIDNEY__ cm
Left Kidney: measures __LEFT_KIDNEY__ cm

Bladder: The urinary bladder is adequately filled. Its wall is not thickened. No evidence of diverticulum or calculus.

{PELVIC_ORGANS}

Colon wall thickness __ mm. Ileal wall thickness __ mm."""

    _PELVIC_ORGANS_FEMALE = "Uterus and Ovaries: The uterus is __UTERUS__ cm size, anteverted shape, homogenous echotexture, myometrium and endometrial thickness __ET__ mm, and ovaries are of normal size."
    _PELVIC_ORGANS_MALE = "Prostate: The prostate gland is normal in size, measuring __PROSTATE__ cm, volume __PROSTATE_VOL__ cc, and shows homogenous echotexture. No focal lesion is seen. Post-void residual urine is minimal."

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

    # (display label, __TOKEN__ name, unit) for the report form's
    # "Measurements" panel — one row per organ blank in the templates
    # above. A field is a harmless no-op if its token isn't in the
    # currently-loaded findings text (wrong scan type, or filled by hand).
    MEASUREMENT_FIELDS = [
        ("Liver",        "LIVER",        "cm"),
        ("Portal Vein",  "PORTAL_VEIN",  "mm"),
        ("CBD",          "CBD",          "mm"),
        ("Spleen",       "SPLEEN",       "cm"),
        ("Right Kidney", "RIGHT_KIDNEY", "cm"),
        ("Left Kidney",  "LEFT_KIDNEY",  "cm"),
        ("Uterus",       "UTERUS",       "cm"),
        ("ET", "ET", "mm"),
        ("Prostate",        "PROSTATE",     "cm"),
        ("Prostate Volume", "PROSTATE_VOL", "cc"),
    ]

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
