from django.contrib import admin
from .models import USGReport 
from .models import (
    # IPD / Ward
    Ward,
    Bed,
    IPDAdmission,

    # Billing
    BillItem,
    PatientService,
    DischargeBill,

    # Procedure Billing
    ProcedureItem,
    ProcedureBill,
    ProcedureBillItem,

    # Core HMS
    Patient,
    Doctor,
    Department,
    Appointment,
    Consultation,

    # Laboratory
    Investigation,
    InvestigationCategory,
    InvestigationParameter,
    InvestigationResult,

    # Clinical Data
    Symptom,
    Sign,
    PastHistory,
    SurgicalHistory,

    # Pharmacy
    DrugMaster,
    Expense,
    ICDCode,
    UserProfile,
    ConstructionExpense,
    Vendor,
    PartnerPayment,
    ExpenseBudget,

    # IPD Discharge Templates
    DischargeTemplate,
    )
# ===================== BASIC MODELS =====================
admin.site.register(Bed)
admin.site.register(IPDAdmission)


# ===================== DISCHARGE TEMPLATES =====================
@admin.register(DischargeTemplate)
class DischargeTemplateAdmin(admin.ModelAdmin):
    list_display = ("procedure_name", "gender", "is_active", "created_at")
    list_filter = ("gender", "is_active")
    search_fields = ("procedure_name",)

# ===================== WARD =====================
@admin.register(Ward)
class WardAdmin(admin.ModelAdmin):
    list_display = ("name", "total_beds")


# ===================== CONSULTATION =====================
@admin.register(Consultation)
class ConsultationAdmin(admin.ModelAdmin):
    list_display = ("id", "appointment", "diagnosis_icd")
    search_fields = ("diagnosis_icd__code", "diagnosis_text")
    list_select_related = ("appointment",)


# ===================== PATIENT =====================
@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("id", "uhid", "full_name", "age", "gender", "mobile_no")
    search_fields = ("full_name", "uhid", "mobile_no")
    list_filter = ("gender",)
    ordering = ("-id",)


# ===================== DEPARTMENT =====================
@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "description")
    search_fields = ("name",)


# ===================== DOCTOR =====================
@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ("id", "full_name", "department", "specialization", "op_fee")
    list_filter = ("department",)
    search_fields = ("full_name", "specialization")


# ===================== APPOINTMENT =====================
@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "patient",
        "doctor",
        "date",
        "time",
        "purpose",
        "created_at",
    )
    list_filter = ("date", "doctor")
    search_fields = ("patient__full_name",)
    date_hierarchy = "date"


# ===================== INVESTIGATION CATEGORY =====================
@admin.register(InvestigationCategory)
class InvestigationCategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)


# ===================== INVESTIGATION PARAMETER INLINE =====================
class InvestigationParameterInline(admin.TabularInline):
    model = InvestigationParameter
    extra = 1
    ordering = ("order",)
    fields = (
        "order",
        "name",
        "unit",
        "min_value",
        "max_value",
        "result_type",
        "group",
        "method",
        "show_in_report",
    )


# ===================== INVESTIGATION =====================
@admin.register(Investigation)
class InvestigationAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "category")
    list_filter = ("category",)
    search_fields = ("name",)
    inlines = [InvestigationParameterInline]


# ===================== INVESTIGATION PARAMETER =====================
@admin.register(InvestigationParameter)
class InvestigationParameterAdmin(admin.ModelAdmin):
    list_display = (
        "investigation",
        "name",
        "unit",
        "loinc_code",
        "loinc_display",
        "min_value",
        "max_value",
        "result_type",
        "order",
        "show_in_report",
    )

    list_filter = (
        "investigation",
        "result_type",
    )

    search_fields = (
        "name",
        "investigation__name",
        "loinc_code",
    )

    fields = (
        "investigation", "name", "unit",
        "loinc_code", "loinc_display",
        "min_value", "max_value",
        "male_range", "female_range",
        "critical_low", "critical_high",
        "result_type", "group", "method",
        "order", "show_in_report",
    )

    ordering = ("investigation", "order")


# ===================== SYMPTOM =====================
@admin.register(Symptom)
class SymptomAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "department", "is_active")
    list_filter = ("department", "is_active")
    search_fields = ("name",)


# ===================== SIGN =====================
@admin.register(Sign)
class SignAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "department", "is_active")
    list_filter = ("department", "is_active")
    search_fields = ("name",)


# ===================== PAST HISTORY =====================
@admin.register(PastHistory)
class PastHistoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


# ===================== SURGICAL HISTORY =====================
@admin.register(SurgicalHistory)
class SurgicalHistoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


# ===================== DRUG MASTER =====================
@admin.register(DrugMaster)
class DrugMasterAdmin(admin.ModelAdmin):

    list_display = (
    "id",
    "name",
    "generic_name",
    "strength",
    "category",
    "atc_code",
    "sort_order",
    "is_active",
    "edit_button",
)

    list_display_links = ("name",)

    list_editable = (
        "sort_order",
        "is_active",
    )

    list_filter = (
        "category",
        "is_active",
    )

    search_fields = (
        "name",
        "generic_name",
    )

    ordering = ("sort_order", "category", "name")

    def edit_button(self, obj):
        from django.utils.html import format_html
        from django.urls import reverse
        url = reverse('admin:hms_drugmaster_change', args=[obj.id])
        return format_html(
            '<a href="{}" style="background:#007676;color:white;padding:4px 14px;'
            'border-radius:5px;text-decoration:none;font-size:12px;font-weight:600;">'
            '✏️ Edit</a>', url
        )
    edit_button.short_description = 'Edit'
# ===================== INVESTIGATION RESULT =====================
@admin.register(InvestigationResult)
class InvestigationResultAdmin(admin.ModelAdmin):

    list_display = (
        "bill_item",
        "parameter",
        "value",
        "entered_by",
        "entered_at",
    )

    search_fields = (
        "parameter__name",
        "entered_by",
        "bill_item__bill__patient__full_name",
        "bill_item__bill__patient__uhid",
    )

    list_filter = (
        "parameter__investigation",
        "entered_at",
    )

    ordering = (
        "-entered_at",
    )

    list_select_related = (
        "parameter",
        "bill_item",
    )


# ===================== BILL ITEM =====================
@admin.register(BillItem)
class BillItemAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price")


# ===================== PATIENT SERVICE =====================
@admin.register(PatientService)
class PatientServiceAdmin(admin.ModelAdmin):
    list_display = ("patient", "item", "quantity", "total", "date")


# ===================== DISCHARGE BILL =====================
@admin.register(DischargeBill)
class DischargeBillAdmin(admin.ModelAdmin):
    list_display = ("patient", "total_amount", "discount", "final_amount", "created_at")


# ===================== PROCEDURE BILLING =====================

class ProcedureBillItemInline(admin.TabularInline):
    model = ProcedureBillItem
    extra = 1


@admin.register(ProcedureBill)
class ProcedureBillAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "patient",
        "consultant",
        "payment_mode",
        "total_amount",
        "net_amount",
        "created_at",
    )

    inlines = [ProcedureBillItemInline]


@admin.register(ProcedureItem)
class ProcedureItemAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "is_active")
    search_fields = ("name",)

from .models import Expense
admin.site.register(Expense)

@admin.register(ICDCode)
class ICDCodeAdmin(admin.ModelAdmin):
    list_display  = ['code', 'description', 'snomed_code', 'snomed_description']
    search_fields = ['code', 'description', 'snomed_code']
    fields = [
        'code', 'description',
        'snomed_code', 'snomed_description',
    ]


# ===================== USER PROFILE =====================
@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display  = ('user', 'role', 'full_name', 'phone', 'is_active')
    list_filter   = ('role', 'is_active')
    search_fields = ('user__username', 'full_name')
    list_editable = ('role',)

from django.utils.html import format_html


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display  = ["name", "mobile", "work_type", "gst_no", "created_at"]
    search_fields = ["name", "mobile", "work_type"]


@admin.register(ConstructionExpense)
class ConstructionExpenseAdmin(admin.ModelAdmin):
    list_display  = [
        "expense_id", "date", "expense_head", "area_location",
        "vendor", "amount", "gst_col", "total_col",
        "approval_badge", "work_status", "material_received",
    ]
    list_filter   = [
        "expense_head", "area_location", "approval_status",
        "work_status", "material_received", "payment_mode", "paid_by",
    ]
    search_fields = ["expense_id", "description", "vendor__name", "bill_no"]
    date_hierarchy = "date"
    readonly_fields = ["expense_id", "gst_amount", "total_amount", "created_at"]

    fieldsets = (
        ("Basic Details", {
            "fields": ("expense_id", "date", "expense_head", "subcategory", "description", "area_location"),
        }),
        ("Vendor & Bill", {
            "fields": ("vendor", "vendor_mobile", "bill_no", "invoice_type"),
        }),
        ("Quantity & Amount", {
            "fields": ("qty", "unit", "rate", "amount", "gst_percent", "gst_amount", "total_amount"),
        }),
        ("Payment", {
            "fields": ("payment_mode", "paid_by", "paid_from", "balance_due", "due_date"),
        }),
        ("Approval & Status", {
            "fields": ("approval_status", "approved_by", "work_status", "material_received"),
        }),
        ("Files & Notes", {
            "fields": ("remarks", "bill_image", "site_photo", "quotation_file"),
        }),
        ("Meta", {"fields": ("created_at",), "classes": ("collapse",)}),
    )

    def gst_col(self, obj):
        return f"₹{obj.gst_amount:,.2f}" if obj.gst_amount else "—"
    gst_col.short_description = "GST"

    def total_col(self, obj):
        return f"₹{obj.total_amount:,.2f}" if obj.total_amount else "—"
    total_col.short_description = "Total"

    def approval_badge(self, obj):
        colors = {
            "Approved": ("#d4edda", "#155724"),
            "Rejected": ("#f8d7da", "#721c24"),
            "Pending":  ("#fff3cd", "#856404"),
        }
        bg, fg = colors.get(obj.approval_status, ("#e2e3e5", "#383d41"))
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;'
            'border-radius:4px;font-size:12px">{}</span>',
            bg, fg, obj.approval_status,
        )
    approval_badge.short_description = "Approval"


@admin.register(PartnerPayment)
class PartnerPaymentAdmin(admin.ModelAdmin):
    list_display  = ["date", "partner_name", "amount_paid", "mode", "reimbursed", "expense_ref"]
    list_filter   = ["partner_name", "reimbursed", "mode"]
    date_hierarchy = "date"

# =====================================================================
# 1. ADD TO admin.py
# =====================================================================

@admin.register(USGReport)
class USGReportAdmin(admin.ModelAdmin):
    list_display  = ("report_no", "patient", "scan_type", "report_date",
                     "impression_status", "reporting_doctor", "is_verified", "created_at")
    list_filter   = ("scan_type", "impression_status", "is_verified", "report_date")
    search_fields = ("report_no", "patient__full_name", "patient__uhid")
    date_hierarchy = "report_date"
    readonly_fields = ("report_no", "created_at", "updated_at")
    list_select_related = ("patient", "reporting_doctor")

    fieldsets = (
        ("Report Identity", {
            "fields": ("report_no", "patient", "scan_type", "report_date", "report_time",
                       "referred_by", "reporting_doctor", "is_verified",
                       "consultation", "bill_item")
        }),
        ("Equipment & Staff", {
            "fields": ("machine_used", "probe_used", "sonographer", "clinical_indication")
        }),
        ("Liver", {"fields": ("liver_size", "liver_echotexture", "liver_lesion", "liver_notes"), "classes": ("collapse",)}),
        ("Gallbladder & CBD", {"fields": ("gb_size", "gb_wall_thickness", "gb_calculi", "gb_calculi_size", "gb_notes", "cbd_diameter", "cbd_notes"), "classes": ("collapse",)}),
        ("Spleen & Pancreas", {"fields": ("spleen_size", "spleen_notes", "pancreas_notes"), "classes": ("collapse",)}),
        ("Kidneys & Bladder", {"fields": ("rt_kidney_size", "rt_kidney_notes", "lt_kidney_size", "lt_kidney_notes", "kidney_calculi", "kidney_calculi_detail", "hydronephrosis", "hydronephrosis_detail", "bladder_notes", "post_void_residue"), "classes": ("collapse",)}),
        ("Gynaecology", {"fields": ("uterus_size", "uterus_position", "uterus_echotexture", "endometrial_thickness", "uterus_notes", "rt_ovary_size", "rt_ovary_notes", "lt_ovary_size", "lt_ovary_notes", "adnexal_notes"), "classes": ("collapse",)}),
        ("Obstetric", {"fields": ("lmp", "ga_by_lmp", "ga_by_scan", "edd_by_lmp", "edd_by_scan", "fetal_presentation", "fetal_heart_rate", "placental_location", "liquor", "afi", "biometry_bpd", "biometry_hc", "biometry_ac", "biometry_fl", "efw", "obstetric_notes"), "classes": ("collapse",)}),
        ("Prostate", {"fields": ("prostate_size", "prostate_notes"), "classes": ("collapse",)}),
        ("Thyroid", {"fields": ("thyroid_rt", "thyroid_lt", "thyroid_isthmus", "thyroid_notes"), "classes": ("collapse",)}),
        ("Breast", {"fields": ("breast_rt", "breast_lt", "breast_notes"), "classes": ("collapse",)}),
        ("Ascites & Other", {"fields": ("ascites", "ascites_detail", "additional_findings")}),
        ("Impression", {"fields": ("impression_status", "impression", "advice")}),
        ("Metadata", {"fields": ("created_by", "created_at", "updated_at"), "classes": ("collapse",)}),
    )


# =====================================================================
# 2. MIGRATION COMMANDS
#    Run in terminal after adding USGReport to models.py:
# =====================================================================
#
#   python manage.py makemigrations hms
#   python manage.py migrate
#
# =====================================================================
# 3. QUICK INTEGRATION TIPS
# =====================================================================
#
# A) Link from the Lab Pending Orders page (lab_report_print.html):
#    If bill_item.investigation.category.dept_code == "RADIOLOGY", show:
#
#    <a href="{% url 'hms:usg_report_create_bill' bill_item.id %}">
#      Generate USG Report
#    </a>
#
# B) Link from Patient profile page:
#
#    <a href="{% url 'hms:usg_report_create_patient' patient.id %}">
#      New USG Report
#    </a>
#
# C) Show USG reports in patient file (ipd_patient_file.html or OPD):
#
#    {% for usg in patient.usg_reports.all %}
#      <a href="{% url 'hms:usg_report_print' usg.pk %}">{{ usg.report_no }}</a>
#    {% endfor %}
#
# =====================================================================
@admin.register(ExpenseBudget)
class ExpenseBudgetAdmin(admin.ModelAdmin):
    list_display = ["expense_head", "budget_amount", "actual_col", "remaining_col", "status_badge"]

    def actual_col(self, obj):
        return f"₹{obj.actual_spent():,.2f}"
    actual_col.short_description = "Actual Spent"

    def remaining_col(self, obj):
        diff = obj.difference()
        color = "green" if diff >= 0 else "red"
        return format_html('<span style="color:{};font-weight:600">₹{:,.2f}</span>', color, diff)
    remaining_col.short_description = "Remaining"

    def status_badge(self, obj):
        s = obj.status()
        bg = "#d4edda" if "Within" in s else "#f8d7da"
        fg = "#155724" if "Within" in s else "#721c24"
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;'
            'border-radius:4px;font-size:12px">{}</span>',
            bg, fg, s,
        )
    status_badge.short_description = "Status"