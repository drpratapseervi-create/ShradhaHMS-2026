from django.contrib import admin
from .models import Admission, ChargeItem, AdvancePayment, FinalBill
@admin.register(Admission)
class AdmissionAdmin(admin.ModelAdmin):
    list_display = ("id","patient_name","mrn","ward","bed","category","doctor","admit_at","discharge_at")
    search_fields = ("patient_name","mrn","reg_no","doctor","ward","bed","category")
    list_filter = ("category","ward","admit_at","discharge_at")

@admin.register(ChargeItem)
class ChargeItemAdmin(admin.ModelAdmin):
    list_display = ("admission","date","type","particulars","qty","rate","amount","sac_code")
    list_filter = ("type","date")
    search_fields = ("particulars","sac_code","admission__patient_name")

@admin.register(AdvancePayment)
class AdvancePaymentAdmin(admin.ModelAdmin):
    list_display = ("admission", "date", "amount", "display_receipt_no", "display_notes")
    list_filter = ("date", "mode")                # quick filter by payment mode
    search_fields = ("ref_no", "note", "admission__patient_name")
    date_hierarchy = "date"                       # month/day navigation
    ordering = ("-date", "-id")

    def display_receipt_no(self, obj):
        return obj.ref_no or "—"
    display_receipt_no.short_description = "Receipt No"

    def display_notes(self, obj):
        return obj.note or "—"
    display_notes.short_description = "Notes"



# admin.py — FinalBillAdmin
@admin.register(FinalBill)
class FinalBillAdmin(admin.ModelAdmin):
    list_display = ("admission","bill_no","gross","discount","cgst","sgst",
                    "net_amount","advance_total","net_payable","created_at")
    readonly_fields = ("created_at",)

    def has_add_permission(self, request):
        # Prevent manual creation in admin; your views auto-create it per Admission
        return False

