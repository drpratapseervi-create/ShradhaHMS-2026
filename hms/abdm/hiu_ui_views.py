"""
Doctor-facing UI for ABDM M3 (HIU role): requesting a patient's records
from other ABDM-connected facilities, tracking consent status, pulling
the actual data once granted, and viewing what came back. See
hms/abdm/services/hiu.py for the actual ABDM calls these views trigger.
"""

import json
from datetime import datetime, time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone as dj_timezone
from django.views.decorators.http import require_POST

from hms.abdm.services.hiu import HIUService
from hms.models import (
    Patient, ABDMConsentRequest, ABDMConsentArtefact,
    ABDMHealthInformationRequest, ABDMReceivedRecord,
)

# The subset of ABDM's purpose-of-use codes relevant to routine clinical
# care (M3 doc §4.3.1) -- ABDM defines more, but these cover why a
# hospital would actually pull another facility's records for a patient.
PURPOSE_CHOICES = [
    ("CAREMGT", "Care Management"),
    ("BTG",     "Break the Glass"),
    ("PATRQT",  "Self-Requested"),
]

HI_TYPE_CHOICES = [
    "Prescription", "DiagnosticReport", "OPConsultation", "DischargeSummary",
    "ImmunizationRecord", "HealthDocumentRecord", "WellnessRecord",
]


@login_required
def hiu_consent_request_form(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)

    doctor = getattr(getattr(request.user, "profile", None), "doctor", None)

    if request.method == "POST":
        hi_types = request.POST.getlist("hi_types")
        date_from_str = request.POST.get("date_from")
        date_to_str = request.POST.get("date_to")
        hip_id = request.POST.get("hip_id", "").strip()
        purpose_code = request.POST.get("purpose_code", "CAREMGT")
        requester_name = request.POST.get("requester_name", "").strip()
        requester_id_type = request.POST.get("requester_id_type", "REGNO").strip()
        requester_id_value = request.POST.get("requester_id_value", "").strip()
        requester_id_system = request.POST.get("requester_id_system", "https://www.mciindia.org").strip()

        if not patient.abha_address:
            messages.error(request, "Patient has no ABHA address on file -- cannot request their records.")
            return redirect("hms:hiu_consent_request_form", patient_id=patient.id)
        if not hi_types:
            messages.error(request, "Select at least one record type to request.")
            return redirect("hms:hiu_consent_request_form", patient_id=patient.id)
        if not (date_from_str and date_to_str and requester_name):
            messages.error(request, "Date range and requester name are required.")
            return redirect("hms:hiu_consent_request_form", patient_id=patient.id)

        # Made timezone-aware in the *local* zone (not UTC) -- combining with
        # UTC directly here rolled date_to's 23:59:59 into the next calendar
        # day once rendered back in Asia/Kolkata (confirmed while testing the
        # form: a "31 Dec 2026" end date displayed as "01 Jan 2027").
        date_from = dj_timezone.make_aware(datetime.combine(datetime.strptime(date_from_str, "%Y-%m-%d").date(), time.min))
        date_to   = dj_timezone.make_aware(datetime.combine(datetime.strptime(date_to_str, "%Y-%m-%d").date(), time.max))

        purpose_text = dict(PURPOSE_CHOICES).get(purpose_code, "Care Management")

        try:
            HIUService.request_consent(
                patient, hi_types=hi_types, date_from=date_from, date_to=date_to,
                requester_name=requester_name, requester_id_type=requester_id_type,
                requester_id_value=requester_id_value, requester_id_system=requester_id_system,
                purpose_code=purpose_code, purpose_text=purpose_text, hip_id=hip_id,
            )
        except ValueError as e:
            messages.error(request, str(e))
            return redirect("hms:hiu_consent_request_form", patient_id=patient.id)

        messages.success(request, "Consent request sent -- the patient will see it in their ABHA app.")
        return redirect("hms:hiu_consent_list", patient_id=patient.id)

    return render(request, "abdm/hiu_consent_request_form.html", {
        "patient": patient,
        "purpose_choices": PURPOSE_CHOICES,
        "hi_type_choices": HI_TYPE_CHOICES,
        "default_requester_name": doctor.full_name if doctor else "",
        "default_requester_id_value": doctor.registration_no if doctor else "",
    })


@login_required
def hiu_consent_list(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    consent_requests = (
        ABDMConsentRequest.objects.filter(patient=patient)
        .prefetch_related("artefacts", "artefacts__hi_requests")
    )
    return render(request, "abdm/hiu_consent_list.html", {
        "patient": patient,
        "consent_requests": consent_requests,
    })


@login_required
@require_POST
def hiu_request_health_information(request, artefact_id):
    artefact = get_object_or_404(ABDMConsentArtefact, id=artefact_id)

    if artefact.status != "GRANTED":
        messages.error(request, f"Consent artefact is '{artefact.status}', not GRANTED -- cannot request data yet.")
        return redirect("hms:hiu_consent_list", patient_id=artefact.consent_request.patient_id)

    try:
        HIUService.request_health_information(artefact)
        messages.success(request, "Data request sent -- records will arrive once the HIP responds.")
    except ValueError as e:
        messages.error(request, str(e))

    return redirect("hms:hiu_consent_list", patient_id=artefact.consent_request.patient_id)


@login_required
def hiu_received_records(request, hi_request_id):
    hi_request = get_object_or_404(
        ABDMHealthInformationRequest.objects.select_related("consent_artefact__consent_request__patient"),
        id=hi_request_id,
    )
    records = ABDMReceivedRecord.objects.filter(hi_request=hi_request)

    pretty_records = []
    for record in records:
        pretty_json = None
        if record.fhir_bundle:
            try:
                pretty_json = json.dumps(json.loads(record.fhir_bundle), indent=2)
            except (json.JSONDecodeError, TypeError):
                pretty_json = record.fhir_bundle
        pretty_records.append({"record": record, "pretty_json": pretty_json})

    return render(request, "abdm/hiu_received_records.html", {
        "hi_request": hi_request,
        "patient": hi_request.consent_artefact.consent_request.patient,
        "pretty_records": pretty_records,
    })
