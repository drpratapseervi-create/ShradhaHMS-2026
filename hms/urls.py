from django.urls import path
from . import views
from .views import ipd_dashboard
from hms.abdm import views as abdm_views

app_name = "hms"

urlpatterns = [

    # ── DASHBOARD ──────────────────────────────────────
    path("", views.dashboard, name="dashboard"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/doctor/", views.doctor_dashboard, name="doctor_dashboard"),
    path("dashboard/nursing/", views.nursing_dashboard, name="nursing_dashboard"),

    # ── PATIENT ────────────────────────────────────────
    path("patients/new/", views.patient_create, name="patient_create"),
    path("opd-register/", views.opd_register, name="opd_register"),
    path("patients/<int:pk>/edit/", views.patient_update, name="patient_update"),
    path("villages/add/", views.add_village, name="add_village"),
    
    # ── APPOINTMENT ────────────────────────────────────
    path("appointments/new/", views.appointment_create, name="appointment_create"),
    path("appointments/get-doctors/", views.get_doctors, name="get_doctors"),
    path('patients/api/get/', views.patient_get_api, name='patient_get_api'),
    # ── OPD ────────────────────────────────────────────
    path("opd/<int:appointment_id>/print/", views.print_opd, name="print_opd"),
    path("opd/export/", views.export_opd_csv, name="opd_export"),

    # ── CONSULTATION ───────────────────────────────────
    path("consultation/<int:appointment_id>/", views.start_consultation, name="start_consultation"),
    path("consultation/<int:appointment_id>/pdf/", views.consultation_pdf, name="consultation_pdf"),
    path("consultation/<int:appointment_id>/lama-consent/print/", views.lama_consent_print, name="lama_consent_print"),
    path("generate-lama-consent/", views.generate_lama_consent, name="generate_lama_consent"),
    path("ai-full-opd/", views.ai_full_opd, name="ai_full_opd"),
    path('prescriptions/template/save/',          views.save_prescription_template,  name='save_prescription_template'),
    path('prescriptions/template/list/',          views.list_prescription_templates,  name='list_prescription_templates'),
    path('prescriptions/template/load/<int:pk>/', views.load_prescription_template,   name='load_prescription_template'),
    path('prescriptions/template/delete/<int:pk>/', views.delete_prescription_template, name='delete_prescription_template'),
    path('symptoms/add/',       views.add_symptom,   name='add_symptom'),
    path('symptoms/delete/<int:pk>/', views.delete_symptom, name='delete_symptom'),
    path('signs/add/',          views.add_sign,      name='add_sign'),
    path('signs/delete/<int:pk>/',    views.delete_sign,   name='delete_sign'),
    path('past-history/add/',         views.add_past_history,    name='add_past_history'),
    path('past-history/delete/<int:pk>/', views.delete_past_history, name='delete_past_history'),
    path('surgical-history/add/',     views.add_surgical_history,    name='add_surgical_history'),
    path('surgical-history/delete/<int:pk>/', views.delete_surgical_history, name='delete_surgical_history'),
    path('advice-options/add/',       views.add_advice_option,    name='add_advice_option'),
    path('advice-options/delete/<int:pk>/', views.delete_advice_option, name='delete_advice_option'),
    path('diet-options/add/',         views.add_diet_option,    name='add_diet_option'),
    path('diet-options/delete/<int:pk>/', views.delete_diet_option, name='delete_diet_option'),
    path('drugs/add-quick/', views.add_drug_quick, name='add_drug_quick'),
    path('drugs/defaults/', views.drug_defaults, name='drug_defaults'),
    path('generate-ai-medicines/', views.generate_ai_medicines, name='generate_ai_medicines'),
    path('generate-diet/', views.generate_diet, name='generate_diet'),
    # ── SEARCH (AJAX) ──────────────────────────────────
    path("medicine-search/", views.medicine_search, name="medicine_search"),
    path("icd-search/", views.icd_search, name="icd_search"),

    # ── LAB ────────────────────────────────────────────
    path("lab/billing/", views.lab_billing_direct, name="lab_billing_direct"),
    path("lab/billing/<int:consultation_id>/", views.lab_billing_direct, name="lab_billing_consultation"),
    path("lab/pending/", views.pending_lab_orders, name="pending_lab_orders"),
    path("lab/bill/mark-paid/<int:bill_id>/", views.lab_mark_paid, name="lab_mark_paid"),
    path("lab/result-entry/<int:bill_item_id>/", views.lab_result_entry, name="lab_result_entry"),
    path("lab/reports/", views.lab_reports, name="lab_reports"),
    path("lab/report/print/<int:bill_item_id>/", views.lab_report_print, name="lab_report_print"),
    path("lab/bill/print/<int:bill_id>/", views.lab_bill_print, name="lab_bill_print"),
    path("lab/radiology/", views.radiology_upload, name="radiology_upload"),

    # ── OTHER ──────────────────────────────────────────
    path("whatsapp/webhook/", views.whatsapp_webhook, name="whatsapp_webhook"),
    path("medical/upload/<int:patient_id>/", views.upload_medical_image, name="upload_medical_image"),
    path("medical/upload/<int:patient_id>/consultation/<int:consultation_id>/",
         views.upload_medical_image_consultation, name="upload_medical_image_consultation"),
    path("medical/image/delete/<int:image_id>/", views.delete_medical_image, name="delete_medical_image"),

    # ── IPD ────────────────────────────────────────────
    path("ipd/", views.ipd_dashboard, name="ipd_dashboard"),
    path("ipd/admit/<int:bed_id>/", views.admit_bed, name="admit_bed"),
    path("ipd/new/", views.admit_patient, name="admit_patient"),
    path("patients/<int:patient_id>/recent-consultation/", views.patient_recent_consultation_api, name="patient_recent_consultation_api"),
    path("ipd/discharge/<int:admission_id>/", views.ipd_discharge, name="ipd_discharge"),
    path("ipd/patient/<int:admission_id>/", views.ipd_patient_file, name="ipd_patient_file"),
    path("ipd/discharge/<int:admission_id>/pdf/", views.discharge_pdf, name="discharge_pdf"),
    path("ipd/progress-notes/<int:admission_id>/pdf/", views.progress_notes_pdf, name="progress_notes_pdf"),
    path("ot/", views.ot_dashboard, name="ot_dashboard"),
    path("ot/new/", views.ot_create, name="ot_create"),
    path("ot/<int:id>/", views.ot_detail, name="ot_detail"),
    path("api/patient-search/", views.patient_search_api, name="patient_search_api"),
    path("ot/<int:id>/edit/", views.ot_edit, name="ot_edit"),
    path("ot/<int:id>/cancel/", views.ot_cancel, name="ot_cancel"),
    path("ot/<int:id>/status/", views.ot_status_update, name="ot_status_update"),
    path("ot/<int:id>/notes/", views.ot_notes, name="ot_notes"),
    path("ot/<int:id>/print/", views.ot_print, name="ot_print"),
    # ── BILLING ────────────────────────────────────────
    path("discharge-bill/<int:patient_id>/", views.discharge_bill, name="discharge_bill"),
    path("delete-bill-item/<int:item_id>/", views.delete_bill_item, name="delete_bill_item"),
    path("discharge-bill-pdf/<int:admission_id>/", views.discharge_bill_pdf, name="discharge_bill_pdf"),
    path("billing/procedure/", views.procedure_billing, name="procedure_billing"),
    path("billing/procedure/print/<int:bill_id>/", views.procedure_bill_print, name="procedure_bill_print"),
    path("advance-receipt/<int:patient_id>/", views.advance_payment_receipt, name="advance_payment_receipt"),
    path("advance-receipt/single/<int:advance_id>/", views.advance_payment_receipt_single, name="advance_payment_receipt_single"),
    path("final-payment-receipt/<int:patient_id>/", views.final_payment_receipt, name="final_payment_receipt"),
    path("daily-report/", views.daily_report, name="daily_report"),
    path("billing/procedure/print/<int:bill_id>/", views.procedure_bill_print, name="procedure_print"),
    path("billing/procedure/list/", views.procedure_pending_list, name="procedure_pending"),
    path("reports/all/", views.all_reports, name="all_reports"),
    path("reports/export/csv/", views.export_all_csv, name="export_all_csv"),
    path("reports/export/excel/", views.export_all_excel, name="export_all_excel"),
    path("reports/export/pdf/", views.export_all_pdf, name="export_all_pdf"),
    # ══════════════════════════════════════════════════
    # ABDM M1 — ABHA CREATION & VERIFICATION
    # ══════════════════════════════════════════════════

    path("abdm/abha/aadhaar/<int:patient_id>/",
         abdm_views.abha_aadhaar_otp, name="abha_aadhaar_otp"),
    path("abdm/abha/verify-otp/<int:patient_id>/",
         abdm_views.abha_verify_otp, name="abha_verify_otp"),
    path("abdm/abha/address/<int:patient_id>/",
         abdm_views.abha_create_address, name="abha_create_address"),
    path("abdm/abha/card/<int:patient_id>/",
         abdm_views.abha_download_card, name="abha_download_card"),
    path("abdm/abha/driving-license/<int:patient_id>/",
         abdm_views.abha_driving_license, name="abha_driving_license"),
    path("abdm/abha/verify-returning/<int:patient_id>/",
         abdm_views.abha_verify_returning, name="abha_verify_returning"),
    path("abdm/abha/link/<int:patient_id>/",
         abdm_views.abha_link_existing, name="abha_link_existing"),

    # ══════════════════════════════════════════════════
    # ABDM M2 — HIP: PUSH RECORDS
    # ══════════════════════════════════════════════════

    path("abdm/push/consultation/<int:consultation_id>/",
         abdm_views.push_care_context, name="push_care_context"),
    path("abdm/push/lab/<int:bill_item_id>/",
         abdm_views.push_lab_report, name="push_lab_report"),

    # ══════════════════════════════════════════════════
    # ABDM M2 — CALLBACKS (ABDM gateway calls these)
    # ══════════════════════════════════════════════════

    # Discovery & Linking
    path("abdm/on-discover/",     abdm_views.abdm_on_discover,     name="abdm_on_discover"),
    path("abdm/on-init/",         abdm_views.abdm_on_init,         name="abdm_on_init"),
    path("abdm/on-confirm/",      abdm_views.abdm_on_confirm,      name="abdm_on_confirm"),

    # Consent
    path("abdm/consent/notify/",  abdm_views.abdm_consent_notify,  name="abdm_consent_notify"),

    # Health Data Request
    path("abdm/data-request/",    abdm_views.abdm_data_request,    name="abdm_data_request"),

    # ══════════════════════════════════════════════════
    # UHI
    # ══════════════════════════════════════════════════
    path("uhi/search/",  abdm_views.uhi_search,  name="uhi_search"),
    path("uhi/confirm/", abdm_views.uhi_confirm, name="uhi_confirm"),

    # ── INVENTORY ─────────────────────────────────────────
    path("inventory/", views.inventory_dashboard, name="inventory_dashboard"),
    path("inventory/items/", views.inventory_items, name="inventory_items"),
    path("inventory/items/new/", views.inventory_item_new, name="inventory_item_new"),
    path("inventory/items/<int:id>/", views.inventory_item_detail, name="inventory_item_detail"),
    path("inventory/stock-in/", views.stock_in_create, name="stock_in_create"),
    path("inventory/stock-out/", views.stock_out_create, name="stock_out_create"),
    path("inventory/suppliers/", views.supplier_list, name="supplier_list"),
    path("inventory/suppliers/new/", views.supplier_new, name="supplier_new"),
    path("inventory/report/", views.inventory_report, name="inventory_report"),

    # ── DOCUMENTS ─────────────────────────────────────────
    path("documents/", views.document_dashboard, name="document_dashboard"),
    path("documents/list/", views.document_list, name="document_list"),
    path("documents/add/", views.document_add, name="document_add"),
    path("documents/<int:doc_id>/edit/", views.document_edit, name="document_edit"),
    path("documents/<int:doc_id>/delete/", views.document_delete, name="document_delete"),
    path("documents/types/", views.document_types_ajax, name="document_types_ajax"),

    # ── USG REPORTS ───────────────────────────────────────────────────
    path("usg/",                                views.usg_report_list,    name="usg_report_list"),
    path("usg/new/",                            views.usg_report_create,  name="usg_report_create"),
    path("usg/new/patient/<int:patient_id>/",   views.usg_report_create,  name="usg_report_create_patient"),
    path("usg/new/bill/<int:bill_item_id>/",    views.usg_report_create,  name="usg_report_create_bill"),
    path("usg/<int:pk>/edit/",                  views.usg_report_edit,    name="usg_report_edit"),
    path("usg/<int:pk>/print/",                 views.usg_report_print,   name="usg_report_print"),
    path("usg/<int:pk>/pdf/",                   views.usg_report_pdf,     name="usg_report_pdf"),
    path("usg/<int:pk>/delete/",                views.usg_report_delete,  name="usg_report_delete"),
    path("patients/<int:pk>/gender/", views.patient_gender_api, name="patient_gender_api"),
    # ── CONSTRUCTION EXPENSES ─────────────────────────────────
    path("construction/",                          views.construction_expense_list,   name="construction_expense_list"),
    path("construction/new/",                      views.construction_expense_create, name="construction_expense_create"),
    path("construction/<int:pk>/edit/",            views.construction_expense_edit,   name="construction_expense_edit"),
    path("construction/<int:pk>/delete/",          views.construction_expense_delete, name="construction_expense_delete"),
    path("api/vendor-search/",                     views.vendor_search_ajax,          name="vendor_search_ajax"),
    path("construction/<int:pk>/receipt/", views.construction_expense_receipt, name="construction_expense_receipt"),
    path("construction/deposits/", views.partner_deposits, name="partner_deposits"),
    path("construction/deposits/<int:pk>/edit/", views.partner_deposit_edit, name="partner_deposit_edit"),
    path("construction/deposits/<int:pk>/delete/", views.partner_deposit_delete, name="partner_deposit_delete"),
]