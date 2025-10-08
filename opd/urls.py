from django.urls import path
from . import views

app_name = "opd"

urlpatterns = [
    # Receipt/print style routes (keep if you already used them)
    path("<int:appointment_id>/print/", views.opd_prescription, name="opd_print"),
    path("<int:appointment_id>/print.pdf", views.opd_prescription_pdf, name="opd_print_pdf"),

    # Prescription routes (your main use)
    path("<int:appointment_id>/prescription/", views.opd_prescription, name="opd_prescription"),
    path("<int:appointment_id>/prescription.pdf", views.opd_prescription_pdf, name="opd_prescription_pdf"),
]
