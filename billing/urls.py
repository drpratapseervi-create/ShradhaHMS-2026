# C:\ShradhaHMS_Full\ShradhaHMS_Full\billing\urls.py
from django.urls import path
from . import views

app_name = "billing"

urlpatterns = [
    path("ping/", views.ping, name="ping"),

    # Admissions
    path("", views.admission_list, name="admission_list"),
    path("new/", views.admission_create, name="admission_create"),
    path("<int:pk>/", views.admission_detail, name="admission_detail"),

    # Add charge / advance to an admission
    path("<int:admission_id>/charge/add/", views.charge_add, name="charge_add"),
    path("<int:admission_id>/advance/add/", views.advance_add, name="advance_add"),

    # Final bill & summary
    path("<int:admission_id>/final/edit/", views.finalbill_edit, name="finalbill_edit"),
    path("<int:admission_id>/summary/", views.bill_summary, name="bill_summary"),
    path("<int:admission_id>/pdf/", views.bill_pdf, name="bill_pdf"),

    # Single charge slip (HTML + PDF)
    path("charge/<int:charge_id>/slip/", views.charge_slip, name="charge_slip"),
    path("charge/<int:charge_id>/slip.pdf", views.charge_slip_pdf, name="charge_slip_pdf"),

    # Single advance (payment) slip (HTML + PDF)
    path("advance/<int:advance_id>/slip/", views.advance_slip, name="advance_slip"),
    path("advance/<int:advance_id>/slip.pdf", views.advance_slip_pdf, name="advance_slip_pdf"),
]
