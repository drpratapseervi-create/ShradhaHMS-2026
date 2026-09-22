"""
WhatsApp (Meta Cloud API) messaging — OPD visit and IPD discharge patient
notifications.
"""

import logging
import re
from datetime import datetime

import requests
from django.conf import settings

logger = logging.getLogger("hms.services.whatsapp")

GRAPH_BASE_URL = "https://graph.facebook.com"


class WhatsAppSendError(Exception):
    """Raised when the Meta Cloud API rejects or fails to send a message."""

    def __init__(self, message, status_code=None, response_body=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


def normalize_indian_mobile(mobile_no):
    """
    Patient.mobile_no is stored as a bare 10-digit number (no country code).
    WhatsApp's Cloud API expects the recipient in E.164 without the leading
    '+' (e.g. '919876543210'). Returns None if the number can't be normalized.
    """
    digits = re.sub(r"\D", "", mobile_no or "")
    if len(digits) == 10:
        return "91" + digits
    if len(digits) == 12 and digits.startswith("91"):
        return digits
    if len(digits) == 13 and digits.startswith("091"):
        return "91" + digits[3:]
    return None


def send_whatsapp_template(to, template_name, language_code=None, body_params=None):
    """
    Send an approved WhatsApp template message via Meta's Cloud API.

    - to: recipient in E.164 without '+', e.g. '919876543210'
    - template_name: approved template name, e.g. 'opd_visit_thankyou'
    - body_params: ordered list of strings filling the template's {{1}}, {{2}}, ...
    """
    if not settings.WHATSAPP_ENABLED:
        raise WhatsAppSendError("WhatsApp is not configured (missing access token / phone number id).")

    language_code = language_code or settings.WHATSAPP_TEMPLATE_LANG

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
        },
    }
    if body_params:
        payload["template"]["components"] = [
            {
                "type": "body",
                "parameters": [{"type": "text", "text": str(p)} for p in body_params],
            }
        ]

    url = f"{GRAPH_BASE_URL}/{settings.WHATSAPP_API_VERSION}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    try:
        resp = requests.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"},
            timeout=15,
        )
    except requests.RequestException as exc:
        logger.exception("WhatsApp send failed (network error) to %s template=%s", to, template_name)
        raise WhatsAppSendError(f"Network error sending WhatsApp message: {exc}") from exc

    if resp.status_code >= 400:
        logger.error(
            "WhatsApp send failed (%s) to %s template=%s: %s",
            resp.status_code, to, template_name, resp.text,
        )
        raise WhatsAppSendError(
            f"Meta API returned {resp.status_code}",
            status_code=resp.status_code,
            response_body=resp.text,
        )

    data = resp.json()
    logger.info("WhatsApp template '%s' sent to %s: %s", template_name, to, data)
    return data


OPD_THANKYOU_TEMPLATE = "opd_visit_thankyou_uhid_datetime"


def send_opd_visit_thankyou(appointment):
    """
    Send the approved 'opd_visit_thankyou_uhid_datetime' template for a
    completed OPD appointment. The template body is:

        Hello {{1}},
        Thank you for visiting Shradha Hospital & Multispeciality Centre, Pali.
        UHID: {{2}}
        Date/Time: {{3}}

    Raises WhatsAppSendError on failure; raises ValueError if the patient's
    mobile number can't be normalized.
    """
    patient = appointment.patient
    to = normalize_indian_mobile(patient.mobile_no)
    if not to:
        raise ValueError(f"Cannot normalize mobile number for WhatsApp: {patient.mobile_no!r}")

    visit_dt = datetime.combine(appointment.date, appointment.time)
    visit_dt_str = visit_dt.strftime("%d/%m/%Y %I:%M %p")

    return send_whatsapp_template(
        to=to,
        template_name=OPD_THANKYOU_TEMPLATE,
        body_params=[patient.full_name, patient.uhid, visit_dt_str],
    )


CONSULTATION_STARTED_TEMPLATE = "consultation_started"


def send_consultation_started(appointment):
    """
    Send the approved 'consultation_started' template the moment a patient's
    OPD consultation begins (the Consultation record is created for their
    appointment -- see start_consultation). The template body is:

        Hello {{1}}, your OPD consultation has started with Dr. {{2}} at
        Shradha Hospital & Multispeciality Centre, Pali. Your UHID is
        {{3}}. Please keep this for your records.

    Raises WhatsAppSendError on failure; raises ValueError if the patient's
    mobile number can't be normalized.
    """
    patient = appointment.patient
    to = normalize_indian_mobile(patient.mobile_no)
    if not to:
        raise ValueError(f"Cannot normalize mobile number for WhatsApp: {patient.mobile_no!r}")

    return send_whatsapp_template(
        to=to,
        template_name=CONSULTATION_STARTED_TEMPLATE,
        body_params=[patient.full_name, appointment.doctor.full_name, patient.uhid],
    )


APPOINTMENT_REMINDER_TEMPLATE = "appointment_reminder"


def send_appointment_reminder(appointment):
    """
    Send the approved 'appointment_reminder' template for an upcoming
    appointment. The template body is:

        Hello {{1}}, this is a reminder for your appointment with
        Dr. {{2}} at Shradha Hospital & Multispeciality Centre, Pali,
        scheduled on {{3}}. Please arrive 10 minutes early.
        For queries, call 9414122542.

    Raises WhatsAppSendError on failure; raises ValueError if the patient's
    mobile number can't be normalized. Does not touch
    appointment.reminder_sent_at -- the caller marks that on success so a
    partial batch failure doesn't silently mark a case as reminded.
    """
    patient = appointment.patient
    to = normalize_indian_mobile(patient.mobile_no)
    if not to:
        raise ValueError(f"Cannot normalize mobile number for WhatsApp: {patient.mobile_no!r}")

    appt_dt = datetime.combine(appointment.date, appointment.time)
    appt_dt_str = appt_dt.strftime("%d/%m/%Y %I:%M %p")

    return send_whatsapp_template(
        to=to,
        template_name=APPOINTMENT_REMINDER_TEMPLATE,
        body_params=[patient.full_name, appointment.doctor.full_name, appt_dt_str],
    )


DISCHARGE_THANKYOU_TEMPLATE = "discharge_thankyou"


def send_discharge_thankyou(admission):
    """
    Send the approved 'discharge_thankyou' template right after an IPD
    patient's final bill is settled (see discharge_bill's 'mark_paid'
    action). The template body is:

        Hello {{1}}, you have been discharged from Shradha Hospital &
        Multispeciality Centre, Pali. UHID: {{2}}. Please follow your
        discharge advice carefully. {{3}}
        For queries, call 9414122542.

    {{3}} is the follow-up line ("Your follow-up visit is on <date>." or
    "" when no follow_up_date is set on the admission).

    Raises WhatsAppSendError on failure; raises ValueError if the patient's
    mobile number can't be normalized. Does not touch
    admission.discharge_message_sent_at -- the caller marks that on success.
    """
    patient = admission.patient
    to = normalize_indian_mobile(patient.mobile_no)
    if not to:
        raise ValueError(f"Cannot normalize mobile number for WhatsApp: {patient.mobile_no!r}")

    if admission.follow_up_date:
        followup_line = f"Your follow-up visit is on {admission.follow_up_date.strftime('%d/%m/%Y')}."
    else:
        followup_line = "Please contact us to schedule a follow-up visit if advised."

    return send_whatsapp_template(
        to=to,
        template_name=DISCHARGE_THANKYOU_TEMPLATE,
        body_params=[patient.full_name, patient.uhid, followup_line],
    )


DISCHARGE_FOLLOWUP_REMINDER_TEMPLATE = "discharge_followup_reminder"


def send_discharge_followup_reminder(admission):
    """
    Send the approved 'discharge_followup_reminder' template ahead of a
    discharged patient's follow_up_date (see the
    send_discharge_followup_reminders management command). The template
    body is:

        Hello {{1}}, this is a reminder for your follow-up visit at
        Shradha Hospital & Multispeciality Centre, Pali, scheduled on
        {{2}}. Please bring your discharge summary. For queries, call
        9414122542.

    Raises WhatsAppSendError on failure; raises ValueError if the patient's
    mobile number can't be normalized, or if follow_up_date isn't set.
    Does not touch admission.followup_reminder_sent_at -- the caller marks
    that on success so a partial batch failure doesn't silently mark a
    case as reminded.
    """
    patient = admission.patient
    to = normalize_indian_mobile(patient.mobile_no)
    if not to:
        raise ValueError(f"Cannot normalize mobile number for WhatsApp: {patient.mobile_no!r}")
    if not admission.follow_up_date:
        raise ValueError(f"Admission {admission.id} has no follow_up_date set")

    followup_date_str = admission.follow_up_date.strftime("%d/%m/%Y")

    return send_whatsapp_template(
        to=to,
        template_name=DISCHARGE_FOLLOWUP_REMINDER_TEMPLATE,
        body_params=[patient.full_name, followup_date_str],
    )


def upload_whatsapp_media(file_bytes, filename, mime_type="application/pdf"):
    """
    Upload a file to Meta's Media API for attaching to an outgoing message.
    Returns Meta's media id -- valid for a single send, not reusable.
    """
    if not settings.WHATSAPP_ENABLED:
        raise WhatsAppSendError("WhatsApp is not configured (missing access token / phone number id).")

    url = f"{GRAPH_BASE_URL}/{settings.WHATSAPP_API_VERSION}/{settings.WHATSAPP_PHONE_NUMBER_ID}/media"
    try:
        resp = requests.post(
            url,
            data={"messaging_product": "whatsapp"},
            files={"file": (filename, file_bytes, mime_type)},
            headers={"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"},
            timeout=30,
        )
    except requests.RequestException as exc:
        logger.exception("WhatsApp media upload failed (network error) for %s", filename)
        raise WhatsAppSendError(f"Network error uploading WhatsApp media: {exc}") from exc

    if resp.status_code >= 400:
        logger.error("WhatsApp media upload failed (%s) for %s: %s", resp.status_code, filename, resp.text)
        raise WhatsAppSendError(
            f"Meta media upload returned {resp.status_code}",
            status_code=resp.status_code,
            response_body=resp.text,
        )

    return resp.json()["id"]


def send_document_template(to, template_name, media_id, filename, language_code=None, body_params=None):
    """
    Send an approved template whose HEADER component is type DOCUMENT,
    attaching the file behind the given (single-use) media_id.
    """
    if not settings.WHATSAPP_ENABLED:
        raise WhatsAppSendError("WhatsApp is not configured (missing access token / phone number id).")

    language_code = language_code or settings.WHATSAPP_TEMPLATE_LANG

    components = [
        {
            "type": "header",
            "parameters": [{"type": "document", "document": {"id": media_id, "filename": filename}}],
        },
    ]
    if body_params:
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": str(p)} for p in body_params],
        })

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
            "components": components,
        },
    }

    url = f"{GRAPH_BASE_URL}/{settings.WHATSAPP_API_VERSION}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    try:
        resp = requests.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"},
            timeout=15,
        )
    except requests.RequestException as exc:
        logger.exception("WhatsApp document send failed (network error) to %s template=%s", to, template_name)
        raise WhatsAppSendError(f"Network error sending WhatsApp document: {exc}") from exc

    if resp.status_code >= 400:
        logger.error(
            "WhatsApp document send failed (%s) to %s template=%s: %s",
            resp.status_code, to, template_name, resp.text,
        )
        raise WhatsAppSendError(
            f"Meta API returned {resp.status_code}",
            status_code=resp.status_code,
            response_body=resp.text,
        )

    data = resp.json()
    logger.info("WhatsApp document template '%s' sent to %s: %s", template_name, to, data)
    return data


PRESCRIPTION_READY_TEMPLATE = "prescription_ready"


def send_prescription_pdf(appointment, pdf_bytes):
    """
    Upload the given prescription PDF bytes and send them via the approved
    'prescription_ready' document-header template. The caller (the view) is
    responsible for rendering appointment's consultation to PDF bytes --
    this function only handles the WhatsApp upload + send.

    Raises WhatsAppSendError on failure; raises ValueError if the patient's
    mobile number can't be normalized.
    """
    patient = appointment.patient
    to = normalize_indian_mobile(patient.mobile_no)
    if not to:
        raise ValueError(f"Cannot normalize mobile number for WhatsApp: {patient.mobile_no!r}")

    filename = f"Prescription_{patient.uhid}.pdf"
    media_id = upload_whatsapp_media(pdf_bytes, filename=filename)

    return send_document_template(
        to=to,
        template_name=PRESCRIPTION_READY_TEMPLATE,
        media_id=media_id,
        filename=filename,
        body_params=[patient.full_name, appointment.doctor.full_name],
    )


LAB_REPORT_READY_TEMPLATE = "lab_report_ready"


def send_lab_report_pdf(bill_item, pdf_bytes):
    """
    Upload the given lab report PDF bytes and send them via the approved
    'lab_report_ready' document-header template. The caller (the view) is
    responsible for rendering the report to PDF bytes -- this function only
    handles the WhatsApp upload + send.

    Raises WhatsAppSendError on failure; raises ValueError if the patient's
    mobile number can't be normalized.
    """
    patient = bill_item.bill.patient
    to = normalize_indian_mobile(patient.mobile_no)
    if not to:
        raise ValueError(f"Cannot normalize mobile number for WhatsApp: {patient.mobile_no!r}")

    filename = f"LabReport_{patient.uhid}.pdf"
    media_id = upload_whatsapp_media(pdf_bytes, filename=filename)

    return send_document_template(
        to=to,
        template_name=LAB_REPORT_READY_TEMPLATE,
        media_id=media_id,
        filename=filename,
        body_params=[patient.full_name, bill_item.investigation.name],
    )


USG_REPORT_READY_TEMPLATE = "usg_report_ready"


def send_usg_report_pdf(report, pdf_bytes):
    """
    Upload the given USG report PDF bytes and send them via the approved
    'usg_report_ready' document-header template. The caller (the view) is
    responsible for rendering the report to PDF bytes -- this function only
    handles the WhatsApp upload + send.

    Raises WhatsAppSendError on failure; raises ValueError if the patient's
    mobile number can't be normalized.
    """
    patient = report.patient
    to = normalize_indian_mobile(patient.mobile_no)
    if not to:
        raise ValueError(f"Cannot normalize mobile number for WhatsApp: {patient.mobile_no!r}")

    filename = f"USGReport_{patient.uhid}.pdf"
    media_id = upload_whatsapp_media(pdf_bytes, filename=filename)

    return send_document_template(
        to=to,
        template_name=USG_REPORT_READY_TEMPLATE,
        media_id=media_id,
        filename=filename,
        body_params=[patient.full_name, report.get_scan_type_display()],
    )
