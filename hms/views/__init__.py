from .auth import (
    get_user_role,
    redirect_by_role,
    hms_login,
    hms_logout,
    dashboard,
    doctor_dashboard,
    nursing_dashboard,
    get_doctors,
)

from .opd import (
    patient_create,
    appointment_create,
    print_opd,
    start_consultation,
    save_referral_note,
    consultation_pdf,
    lama_consent_print,
    referral_letter_print,
    medical_certificate_print,
    save_medical_certificate,
    save_clinical_scribe,
    export_opd_csv,
    medicine_search,
    icd_search,
    patient_update,
    opd_register,
    patient_search_api,
    patient_gender_api,
    patient_get_api,
    patient_recent_consultation_api,
    add_drug_quick,
    drug_defaults,
    add_village,
)

from .lab import (
    amount_in_words,
    compute_flag,
    build_lab_report_context,
    lab_billing_direct,
    pending_lab_orders,
    lab_mark_paid,
    lab_result_entry,
    lab_reports,
    lab_report_print,
    lab_bill_print,
)

from .catalog import (
    add_symptom,
    delete_symptom,
    add_sign,
    delete_sign,
    add_past_history,
    delete_past_history,
    add_surgical_history,
    delete_surgical_history,
    add_advice_option,
    delete_advice_option,
    add_diet_option,
    delete_diet_option,
    save_prescription_template,
    list_prescription_templates,
    load_prescription_template,
    delete_prescription_template,
)

from .imaging import (
    upload_medical_image,
    upload_medical_image_consultation,
    delete_medical_image,
    radiology_upload,
    usg_report_list,
    usg_report_create,
    usg_report_edit,
    usg_report_print,
    usg_report_pdf,
    usg_report_delete,
)

from .ipd import (
    ipd_dashboard,
    admit_bed,
    ipd_discharge,
    admit_patient,
    procedure_performed_text,
    chief_complaint_text,
    ipd_patient_file,
    discharge_pdf,
    progress_notes_pdf,
)

from .billing import (
    discharge_bill,
    delete_bill_item,
    discharge_bill_pdf,
    advance_payment_receipt,
    advance_payment_receipt_single,
    final_payment_receipt,
    procedure_billing,
    procedure_bill_print,
    procedure_pending_list,
)

from .ot import (
    ot_dashboard,
    ot_create,
    ot_detail,
    ot_edit,
    ot_cancel,
    ot_status_update,
    ot_notes,
    ot_print,
)

from .inventory import (
    inventory_dashboard,
    inventory_report,
    inventory_items,
    inventory_item_new,
    inventory_item_detail,
    stock_in_create,
    stock_out_create,
    supplier_list,
    supplier_new,
)

from .documents import (
    document_dashboard,
    document_list,
    document_add,
    document_edit,
    document_delete,
    document_types_ajax,
)

from .ai import (
    ai_icd_suggest,
    ai_full_opd,
    ai_clinical_review,
    ai_clinical_scribe,
    generate_diet,
    ai_polish_discharge,
    transcribe_dictation,
    generate_lama_consent,
    generate_referral_letter,
    generate_ai_medicines,
)

from .reports import (
    get_dept_display,
    get_all_payment_data,
    all_reports,
    export_all_csv,
    export_all_excel,
    export_all_pdf,
    daily_report,
)

from .construction import (
    construction_expense_list,
    construction_media_upload,
    construction_media_delete,
    construction_expense_create,
    construction_expense_edit,
    construction_expense_delete,
    construction_expense_receipt,
    vendor_search_ajax,
    form_context,
    partner_deposits,
    partner_deposit_edit,
    partner_deposit_delete,
)

from .tpa import (
    tpa_patient_list,
    tpa_patient_create,
    tpa_patient_edit,
    tpa_patient_detail,
    tpa_patient_delete,
    tpa_document_upload,
    tpa_document_delete,
    tpa_scheme_add,
    tpa_scheme_search,
    tpa_import_upload,
    tpa_import_map,
    tpa_import_summary,
    tpa_import_batch_list,
    tpa_import_undo,
)

from .whatsapp import (
    whatsapp_webhook,
)

