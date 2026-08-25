from django import forms
from datetime import date, datetime
from .models import ProcedureBill
from .models import USGReport
from .models import (
    Patient,
    Doctor,
    Department,
    Appointment,
    Consultation,
    ICDCode,
    IPDAdmission,
    IPDVital,
    IPDProgressNote,
)

# ===================== CONSULTATION FORM =====================
class ConsultationForm(forms.ModelForm):

    diagnosis_icd = forms.ModelChoiceField(
        queryset=ICDCode.objects.all().order_by("code"),
        required=False,
        empty_label="Select ICD-10 code"
    )

    class Meta:
        model = Consultation
        exclude = [
            "appointment",
            "symptoms",
            "signs",
            "past_history",
            "surgical_history",
            "surgery_date",
            "investigations",
            "created_at",
            "advice",   
            "diet_advice",
            "follow_up_date",
            "follow_up_notes",
        ]

# ===================== PATIENT FORM =====================
class PatientForm(forms.ModelForm):

    email = forms.EmailField(required=False, label="Email")

    class Meta:
        model = Patient
        fields = "__all__"
        widgets = {
            "date_of_birth": forms.DateInput(
                attrs={
                    "type": "date",
                    "max": date.today().isoformat()
                }
            ),
            "mobile_no": forms.TextInput(attrs={
                "inputmode": "numeric",
                "placeholder": "10-digit number",
                "autocomplete": "off",
            }),
            "address": forms.Textarea(attrs={"rows": 2}),
            "allergy_details": forms.Textarea(attrs={"rows": 2}),
            "chronic_illness": forms.Textarea(attrs={"rows": 2}),
            "abha_number": forms.TextInput(attrs={
                "autocomplete": "off",
                "placeholder": "e.g. 91-1234-5678-9012"
            }),
            "abha_address": forms.TextInput(attrs={
                "autocomplete": "off",
                "placeholder": "e.g. username@abdm"
            }),
        }

    def clean(self):
        cleaned_data = super().clean()

        # Make email optional
        if not cleaned_data.get("email"):
            self.errors.pop("email", None)
            cleaned_data["email"] = ""

        if cleaned_data.get("allergy") and not cleaned_data.get("allergy_details"):
            self.add_error("allergy_details", "Please specify allergy details.")
        if cleaned_data.get("abha_number") and not cleaned_data.get("abha_consent"):
            self.add_error("abha_consent", "ABHA consent required.")
        return cleaned_data

# ===================== APPOINTMENT FORM =====================
class AppointmentForm(forms.ModelForm):

    class Meta:
        model = Appointment
        fields = [
            "patient",
            "department",
            "doctor",
            "date",
            "time",
            "purpose"
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "time": forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields["date"].initial = date.today()
        if not self.instance.pk:
            self.fields["time"].initial = datetime.now().strftime("%H:%M")
        if "department" in self.data:
            self.fields["doctor"].queryset = Doctor.objects.all()
        elif self.instance.pk and self.instance.department:
            self.fields["doctor"].queryset = Doctor.objects.filter(
                department=self.instance.department
            )
        elif not self.is_bound and not self.instance.pk:
            # Default a fresh booking form to General Surgery / Dr. Pratap
            # Senecha, since that's the most common combination — still
            # freely changeable by staff.
            default_dept = Department.objects.filter(name="General Surgery").first()
            if default_dept:
                self.fields["department"].initial = default_dept.pk
                self.fields["doctor"].queryset = Doctor.objects.filter(department=default_dept)
                default_doctor = Doctor.objects.filter(
                    department=default_dept, full_name__icontains="Pratap Senecha"
                ).first()
                if default_doctor:
                    self.fields["doctor"].initial = default_doctor.pk
            else:
                self.fields["doctor"].queryset = Doctor.objects.none()
        else:
            self.fields["doctor"].queryset = Doctor.objects.none()


# ===================== IPD ADMISSION FORM =====================
class IPDAdmissionForm(forms.ModelForm):

    class Meta:
        model = IPDAdmission
        fields = [
            "patient",
            "doctor",
            "ward",
            "bed",
            "chief_complaint",
            "diagnosis",
            "icd_code",
            "attendant_name",
            "attendant_relation",
            "attendant_mobile",
        ]
        widgets = {
            "diagnosis": forms.Textarea(attrs={"rows": 3}),
            "chief_complaint": forms.Textarea(attrs={"rows": 3}),
        }

# ===================== IPD VITAL FORM =====================
class IPDVitalForm(forms.ModelForm):

    class Meta:
        model = IPDVital
        fields = [
            "pulse",
            "bp",
            "temperature",
            "spo2",
            "rr"
        ]
        widgets = {
            "pulse": forms.NumberInput(attrs={"class": "form-control"}),
            "bp": forms.TextInput(attrs={"class": "form-control"}),
            "temperature": forms.NumberInput(attrs={"class": "form-control"}),
            "spo2": forms.NumberInput(attrs={"class": "form-control"}),
            "rr": forms.NumberInput(attrs={"class": "form-control"}),
        }

# ===================== USG REPORT FORM =====================
class USGReportForm(forms.ModelForm):

    class Meta:
        model = USGReport
        exclude = [
            "report_no",
            "created_by",
            "created_at",
            "updated_at",
        ]

        widgets = {
            # ── dates / times ─────────────────────────────────────────
            "report_date":          forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "report_time":          forms.TimeInput(attrs={"type": "time", "class": "form-control"}),
            "lmp":                  forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}),
            "edd_by_lmp":           forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}),
            "edd_by_scan":          forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}),

            # ── selects ───────────────────────────────────────────────
            "patient":              forms.Select(attrs={"class": "form-select"}),
            "scan_type":            forms.Select(attrs={"class": "form-select"}),
            "referred_by":          forms.Select(attrs={"class": "form-select"}),
            "reporting_doctor":     forms.Select(attrs={"class": "form-select"}),
            "consultation":         forms.Select(attrs={"class": "form-select"}),
            "bill_item":            forms.Select(attrs={"class": "form-select"}),
            "impression_status":    forms.Select(attrs={"class": "form-select"}),

            # ── LIVER ─────────────────────────────────────────────────
            "liver_size":           forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "e.g. 14.2"}),
            "liver_echotexture":    forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "liver_lesion":         forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 2}),
            "liver_notes":          forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 2}),

            # ── GALLBLADDER & CBD ─────────────────────────────────────
            "gb_size":              forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "e.g. 8 × 3 cm"}),
            "gb_wall_thickness":    forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "e.g. 3"}),
            "gb_calculi_size":      forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "e.g. 8 mm"}),
            "gb_calculi_detail":    forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "e.g. 8 mm calculus in neck"}),
            "gb_notes":             forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 2}),
            "cbd_diameter":         forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "e.g. 4"}),
            "cbd_notes":            forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 1}),

            # ── SPLEEN & PANCREAS ─────────────────────────────────────
            "spleen_size":          forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "e.g. 10.5"}),
            "spleen_notes":         forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 2}),
            "pancreas_notes":       forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 2}),

            # ── RIGHT KIDNEY ──────────────────────────────────────────
            "rk_size":              forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "e.g. 10.2 × 4.5"}),
            "rk_stone_size":        forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "e.g. 6 mm"}),
            "rk_stone_site":        forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Upper / Mid / Lower pole, PUJ"}),
            "rk_cyst_size":         forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "e.g. 3 cm"}),
            "rk_cyst_location":     forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Upper / Mid / Lower"}),
            "rk_cyst_type":         forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Simple / Complex"}),
            "rt_kidney_size":       forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "rt_kidney_notes":      forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 2}),

            # ── LEFT KIDNEY ───────────────────────────────────────────
            "lk_size":              forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "e.g. 10.7 × 4.2"}),
            "lk_stone_size":        forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "e.g. 6 mm"}),
            "lk_stone_site":        forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Upper / Mid / Lower pole, PUJ"}),
            "lk_cyst_size":         forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "e.g. 3 cm"}),
            "lk_cyst_location":     forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Upper / Mid / Lower"}),
            "lk_cyst_type":         forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Simple / Complex"}),
            "lt_kidney_size":       forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "lt_kidney_notes":      forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 2}),
            "kidney_calculi_detail":forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 2}),
            "hydronephrosis_detail":forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 2}),

            # ── URETERIC CALCULUS ─────────────────────────────────────
            "ureteric_side":        forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "ureteric_size":        forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "e.g. 5 mm"}),
            "ureteric_site":        forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "VUJ / PUJ / Mid-ureter"}),

            # ── BLADDER ───────────────────────────────────────────────
            "bladder_state":        forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "bladder_notes":        forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 2}),
            "post_void_residue":    forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "e.g. 45"}),
            "pvrv":                 forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "e.g. 45"}),

            # ── UTERUS ────────────────────────────────────────────────
            "uterus_size":          forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "uterus_position":      forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "uterus_echotexture":   forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "uterus_myometrium":    forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "endometrial_thickness":forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "e.g. 8"}),
            "uterus_notes":         forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 2}),
            "fibroid_size":         forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "fibroid_site":         forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "fibroid_type":         forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "rt_ovary_size":        forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "rt_ovary_notes":       forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 1}),
            "lt_ovary_size":        forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "lt_ovary_notes":       forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 1}),
            "adnexal_notes":        forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 2}),

            # ── RIGHT OVARY ───────────────────────────────────────────
            "ro_size":              forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Size (cm)"}),
            "ro_volume":            forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Volume (cc)"}),
            "ro_cyst_size":         forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "ro_cyst_type":         forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Simple / Hemorrhagic / Dermoid / Endometrioma"}),

            # ── LEFT OVARY ────────────────────────────────────────────
            "lo_size":              forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Size (cm)"}),
            "lo_volume":            forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Volume (cc)"}),
            "lo_cyst_size":         forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "lo_cyst_type":         forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Simple / Hemorrhagic / Dermoid / Endometrioma"}),

            # ── OBSTETRIC ─────────────────────────────────────────────
            "ga_by_lmp":            forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "ga_by_scan":           forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "fetal_presentation":   forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "fetal_heart_rate":     forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "e.g. 148 bpm"}),
            "placental_location":   forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "liquor":               forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "afi":                  forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "biometry_bpd":         forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "biometry_hc":          forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "biometry_ac":          forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "biometry_fl":          forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "efw":                  forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "obstetric_notes":      forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 2}),

            # ── PROSTATE ──────────────────────────────────────────────
            "prostate_size":        forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "prostate_volume":      forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "e.g. 28 cc"}),
            "prostate_echotexture": forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "prostate_notes":       forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 2}),

            # ── HERNIA ────────────────────────────────────────────────
            "hernia_type":          forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "hernia_side":          forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "hernia_defect_size":   forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "e.g. 2 cm"}),

            # ── APPENDIX ──────────────────────────────────────────────
            "appendix_diameter":    forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "e.g. 7 mm"}),

            # ── BOWEL ─────────────────────────────────────────────────
            "colitis_site":         forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "e.g. Sigmoid / Transverse"}),

            # ── ASCITES & ADDITIONAL ──────────────────────────────────
            "ascites_detail":       forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 2}),
            "additional_findings":  forms.Textarea(attrs={"class": "form-control", "rows": 3}),

            # ── IMPRESSION ────────────────────────────────────────────
            "impression":           forms.Textarea(attrs={"class": "form-control", "rows": 5,
                                        "placeholder": "1. Normal liver and biliary system.\n2. Small calculus in right kidney (6 mm)..."}),
            "advice":               forms.Textarea(attrs={"class": "form-control", "rows": 2}),

            # ── MACHINE / OTHER ───────────────────────────────────────
            "clinical_indication":  forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "sonographer":          forms.TextInput(attrs={"class": "form-control"}),
            "machine_used":         forms.TextInput(attrs={"class": "form-control"}),
            "probe_used":           forms.TextInput(attrs={"class": "form-control"}),
            "thyroid_rt":           forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "thyroid_lt":           forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "thyroid_isthmus":      forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "thyroid_notes":        forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 2}),
            "breast_rt":            forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 3}),
            "breast_lt":            forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 3}),
            "breast_notes":         forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 2}),
        }

# ===================== IPD PROGRESS NOTE FORM =====================
class IPDProgressNoteForm(forms.ModelForm):

    class Meta:
        model = IPDProgressNote
        fields = [
            "subjective",
            "objective",
            "assessment",
            "plan"
        ]
        widgets = {
            "subjective": forms.Textarea(attrs={"rows": 2}),
            "objective":  forms.Textarea(attrs={"rows": 2}),
            "assessment": forms.Textarea(attrs={"rows": 2}),
            "plan":       forms.Textarea(attrs={"rows": 2}),
        }


# ===================== PROCEDURE BILL FORM =====================
class ProcedureBillForm(forms.ModelForm):

    class Meta:
        model = ProcedureBill
        fields = [
            "patient",
            "department",
            "consultant"
        ]