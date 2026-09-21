"""
WhatsApp (Meta Cloud API) messaging — OPD visit patient notifications.
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
