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
            "custom_symptoms",
            "custom_signs",
            "surgery_date",
            "investigations",
            "created_at",
            "advice",
            "diet_advice",
            "follow_up_date",
            "follow_up_notes",
            "lama_declined",
            "lama_diagnosis",
            "lama_plan",
            "lama_consent_en",
            "lama_consent_hi",
            "lama_attendant_name",
            "lama_attendant_relation",
            "lama_signed_name",
            "lama_signature_data",
            "lama_signed_at",
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
            "purpose",
            "fee",
            "payment_mode",
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

    admission_date = forms.DateTimeField(
        required=False,
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local", "class": "form-control"},
        ),
    )

    class Meta:
        model = IPDAdmission
        fields = [
            "patient",
            "doctor",
            "ward",
            "bed",
            "chief_complaint",
            "symptoms",
            "diagnosis",
            "icd_code",
            "admission_date",
            "attendant_name",
            "attendant_relation",
            "attendant_mobile",
        ]
        widgets = {
            "diagnosis": forms.Textarea(attrs={"rows": 3}),
            "chief_complaint": forms.Textarea(attrs={"rows": 3}),
            "symptoms": forms.Textarea(attrs={"rows": 3}),
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

            # ── selects ───────────────────────────────────────────────
            "patient":              forms.Select(attrs={"class": "form-select"}),
            "scan_type":            forms.Select(attrs={"class": "form-select"}),
            "referred_by":          forms.Select(attrs={"class": "form-select"}),
            "reporting_doctor":     forms.Select(attrs={"class": "form-select"}),
            "consultation":         forms.Select(attrs={"class": "form-select"}),
            "bill_item":            forms.Select(attrs={"class": "form-select"}),
            "impression_status":    forms.Select(attrs={"class": "form-select"}),

            # ── MACHINE / OTHER ───────────────────────────────────────
            "clinical_indication":  forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "sonographer":          forms.TextInput(attrs={"class": "form-control"}),
            "machine_used":         forms.TextInput(attrs={"class": "form-control"}),
            "probe_used":           forms.TextInput(attrs={"class": "form-control"}),

            # ── FINDINGS / IMPRESSION / ADVICE ─────────────────────────
            "findings_text":        forms.Textarea(attrs={"class": "form-control", "rows": 1,
                                        "id": "id_findings_text",
                                        "placeholder": "Organ-wise findings — use “Load Standard Template” for the selected scan type, then edit."}),
            "impression":           forms.Textarea(attrs={"class": "form-control", "rows": 4,
                                        "placeholder": "1. Normal study.\n2. ..."}),
            "advice":               forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "is_verified":          forms.CheckboxInput(attrs={"class": "form-check-input"}),
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