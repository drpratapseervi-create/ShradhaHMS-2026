"""
ABDM Milestone 2 — HIP (Health Information Provider) Service
=============================================================
Implements:
1. FHIR R4 Bundle builder  (OPD / Lab / Discharge / Prescription)
2. HIP-initiated linking   (add care context to HIE-CM)
3. Mobile SMS notification (for patients without ABHA address)
4. Discovery & Link        (respond to patient-initiated discovery)
5. Consent management      (store & verify consent artifacts)
6. Health data packaging   (encrypt & transfer on request)
"""

import uuid
import json
import base64
import hashlib
import requests
import random
from datetime import datetime, timezone, timedelta
from django.conf import settings

from .auth import abdm
from . import fidelius


# ═══════════════════════════════════════════════════════
# SECTION 1 — FHIR R4 BUNDLE BUILDER
# ═══════════════════════════════════════════════════════

class FHIRBuilder:
    """
    Builds FHIR R4 Bundles as required by ABDM.
    Supports: OPD Note | Lab Report | Discharge Summary | Prescription
    Standards: https://nrces.in/ndhm
    """

    @staticmethod
    def _patient_resource(patient) -> dict:
        return {
            "resourceType": "Patient",
            "id":           f"patient-{patient.id}",
            "identifier": [
                {
                    "type": {
                        "coding": [{
                            "system":  "http://terminology.hl7.org/CodeSystem/v2-0203",
                            "code":    "MR",
                            "display": "Medical Record Number"
                        }]
                    },
                    "system": "https://healthid.ndhm.gov.in",
                    "value":  patient.abha_number or patient.uhid,
                }
            ],
            "name":   [{"text": patient.full_name}],
            "gender": (patient.gender or "unknown").lower(),
            "telecom": [
                {"system": "phone", "value": patient.mobile_no or ""}
            ],
            "address": [
                {"text": patient.address or ""}
            ],
        }

    @staticmethod
    def _practitioner_resource(doctor) -> dict:
        return {
            "resourceType": "Practitioner",
            "id":           f"doctor-{doctor.id}",
            "name":         [{"text": doctor.full_name}],
            "qualification": [
                {
                    "code": {
                        "coding": [{
                            "system":  "http://snomed.info/sct",
                            "code":    "309343006",
                            "display": "Physician"
                        }]
                    }
                }
            ]
        }

    @staticmethod
    def _organization_resource() -> dict:
        return {
            "resourceType": "Organization",
            "id":           "shradha-hospital",
            "name":         "Shradha Hospital & Multispeciality Centre",
            "telecom": [
                {"system": "phone", "value": "9414122542"}
            ],
            "address": [
                {"text": "Pani Ki Do Tanki, Surajpole, Pali (Rajasthan) – 306401"}
            ],
            "identifier": [
                {
                    "system": "https://facility.ndhm.gov.in",
                    "value":  settings.ABDM_HIP_ID or "UNKNOWN"
                }
            ]
        }

    # ── OPD Consultation Bundle ──────────────────────────

    @staticmethod
    def opd_bundle(consultation, appointment) -> dict:
        """
        FHIR Bundle for OPD Consultation Note.
        HI-Type: OPDischargeNote
        """
        patient   = appointment.patient
        doctor    = appointment.doctor
        now       = datetime.now(timezone.utc).isoformat()
        bundle_id = str(uuid.uuid4())

        # Build prescription entries
        medication_entries = []
        for rx in consultation.prescriptions.all() if hasattr(consultation, 'prescriptions') else []:
            medication_entries.append({
                "resource": {
                    "resourceType":    "MedicationRequest",
                    "id":              str(uuid.uuid4()),
                    "status":          "active",
                    "intent":          "order",
                    "medicationCodeableConcept": {
                        "text": rx.medicine
                    },
                    "subject": {"reference": f"Patient/patient-{patient.id}"},
                    "dosageInstruction": [{
                        "text": f"{rx.dose} {rx.frequency} for {rx.duration}"
                    }]
                }
            })

        # Composition resource
        composition = {
            "resourceType": "Composition",
            "id":           str(uuid.uuid4()),
            "status":       "final",
            "type": {
                "coding": [{
                    "system":  "http://snomed.info/sct",
                    "code":    "371530004",
                    "display": "Clinical consultation report"
                }]
            },
            "subject":  {"reference": f"Patient/patient-{patient.id}"},
            "date":     now,
            "author":   [{"reference": f"Practitioner/doctor-{doctor.id}"}],
            "title":    "OPD Consultation Note",
            "section": [
                {
                    "title": "Chief Complaint",
                    "code": {
                        "coding": [{
                            "system": "http://snomed.info/sct",
                            "code": "422843007",
                            "display": "Chief complaint"
                        }]
                    },
                    "text": {
                        "status": "generated",
                        "div": f"<div>{consultation.diagnosis_text or '-'}</div>"
                    }
                },
                {
                    "title": "Diagnosis",
                    "text": {
                        "status": "generated",
                        "div": f"<div>{consultation.diagnosis_text or '-'}</div>"
                    }
                }
            ]
        }

        return {
            "resourceType": "Bundle",
            "id":           bundle_id,
            "meta":         {"lastUpdated": now},
            "identifier":   {"value": bundle_id},
            "type":         "document",
            "timestamp":    now,
            "entry": [
                {"resource": composition},
                {"resource": FHIRBuilder._patient_resource(patient)},
                {"resource": FHIRBuilder._practitioner_resource(doctor)},
                {"resource": FHIRBuilder._organization_resource()},
            ] + medication_entries
        }

    # ── Lab Report Bundle ────────────────────────────────

    @staticmethod
    def lab_bundle(item, results) -> dict:
        """
        FHIR Bundle for Lab/Diagnostic Report.
        HI-Type: DiagnosticReport
        """
        patient   = item.bill.patient
        now       = datetime.now(timezone.utc).isoformat()
        bundle_id = str(uuid.uuid4())

        # Build observation entries for each result
        observation_entries = []
        for r in results:
            obs = {
                "resourceType": "Observation",
                "id":           str(uuid.uuid4()),
                "status":       "final",
                "code": {
                    "coding": [{"display": r.parameter.name}],
                    "text":   r.parameter.name,
                },
                "subject":     {"reference": f"Patient/patient-{patient.id}"},
                "valueString": str(r.value),
                "referenceRange": [],
            }

            if r.parameter.min_value and r.parameter.max_value:
                obs["referenceRange"] = [{
                    "low":  {"value": float(r.parameter.min_value), "unit": r.parameter.unit or ""},
                    "high": {"value": float(r.parameter.max_value), "unit": r.parameter.unit or ""},
                }]

            observation_entries.append({"resource": obs})

        diagnostic_report = {
            "resourceType": "DiagnosticReport",
            "id":           str(uuid.uuid4()),
            "status":       "final",
            "code": {
                "coding": [{"display": item.investigation.name}],
                "text":   item.investigation.name,
            },
            "subject":  {"reference": f"Patient/patient-{patient.id}"},
            "issued":   now,
            "result":   [
                {"reference": f"Observation/{e['resource']['id']}"}
                for e in observation_entries
            ]
        }

        composition = {
            "resourceType": "Composition",
            "id":           str(uuid.uuid4()),
            "status":       "final",
            "type": {
                "coding": [{
                    "system":  "http://snomed.info/sct",
                    "code":    "4241000179101",
                    "display": "Laboratory report"
                }]
            },
            "subject": {"reference": f"Patient/patient-{patient.id}"},
            "date":    now,
            "title":   f"Lab Report - {item.investigation.name}",
            "section": [
                {
                    "title": "Lab Results",
                    "entry": [
                        {"reference": f"DiagnosticReport/{diagnostic_report['id']}"}
                    ]
                }
            ]
        }

        return {
            "resourceType": "Bundle",
            "id":           bundle_id,
            "type":         "document",
            "timestamp":    now,
            "entry": [
                {"resource": composition},
                {"resource": FHIRBuilder._patient_resource(patient)},
                {"resource": FHIRBuilder._organization_resource()},
                {"resource": diagnostic_report},
            ] + observation_entries
        }

    # ── Prescription Bundle ──────────────────────────────

    @staticmethod
    def prescription_bundle(consultation, appointment) -> dict:
        """
        FHIR Bundle for Prescription.
        HI-Type: Prescription
        """
        patient   = appointment.patient
        doctor    = appointment.doctor
        now       = datetime.now(timezone.utc).isoformat()
        bundle_id = str(uuid.uuid4())

        med_entries = []
        for rx in getattr(consultation, 'prescriptions', []):
            med_entries.append({
                "resource": {
                    "resourceType": "MedicationRequest",
                    "id":     str(uuid.uuid4()),
                    "status": "active",
                    "intent": "order",
                    "medicationCodeableConcept": {"text": rx.medicine},
                    "subject": {"reference": f"Patient/patient-{patient.id}"},
                    "requester": {"reference": f"Practitioner/doctor-{doctor.id}"},
                    "dosageInstruction": [{
                        "text": f"{rx.dose} | {rx.frequency} | {rx.duration} | {rx.instructions}"
                    }]
                }
            })

        composition = {
            "resourceType": "Composition",
            "id":    str(uuid.uuid4()),
            "status": "final",
            "type": {
                "coding": [{
                    "system":  "http://snomed.info/sct",
                    "code":    "440545006",
                    "display": "Prescription record"
                }]
            },
            "subject": {"reference": f"Patient/patient-{patient.id}"},
            "date":    now,
            "title":   "Prescription",
        }

        return {
            "resourceType": "Bundle",
            "id":        bundle_id,
            "type":      "document",
            "timestamp": now,
            "entry": [
                {"resource": composition},
                {"resource": FHIRBuilder._patient_resource(patient)},
                {"resource": FHIRBuilder._practitioner_resource(doctor)},
            ] + med_entries
        }


# ═══════════════════════════════════════════════════════
# SECTION 2 — HIP SERVICE (Linking + Notification)
# ═══════════════════════════════════════════════════════

class HIPService:
    """
    Implements M2 HIP services:
    - HIP-initiated care context linking
    - Mobile SMS notification
    - Discovery response
    - Consent storage and verification
    - Health data packaging and transfer
    """

    # ── HIP Initiated Linking (M2 doc §4) ────────────────

    @staticmethod
    def ensure_care_context_linked(patient, reference_number: str,
                                   display: str, hi_type: str) -> dict:
        """
        Entry point for "a health record was created/updated for this
        patient" — call sites (opd/billing/lab/imaging views) should call
        this rather than the lower-level methods below.

        First time seeing this reference_number: kicks off the async
        generate-link-token -> link-care-context flow (M2 §4.3.1-4.3.4).
        Already linked: sends a care-context-update notify instead
        (M2 §4.3.6 — for genuine edits to an already-linked record).

        Skips silently if the patient has no verified ABHA address.
        """
        if not (patient and patient.abha_address and patient.abha_verified):
            return {}

        from hms.models import ABDMCareContext
        context, _ = ABDMCareContext.objects.get_or_create(
            patient=patient,
            reference_number=reference_number,
            defaults={"display": display, "hi_type": hi_type},
        )

        if context.linked:
            return HIPService.notify_care_context_update(
                patient           = patient,
                patient_reference = str(patient.id),
                care_context_ref  = reference_number,
                hi_type           = hi_type,
            )

        # Not linked yet (brand new, or a previous link attempt never got
        # confirmed) — (re)kick off the async link flow.
        return HIPService.generate_link_token(patient)

    @staticmethod
    def generate_link_token(patient) -> dict:
        """
        Step 1 of HIP-initiated linking. The link token is NOT returned in
        this response — it arrives later via the on-generate-token callback
        (matched by the REQUEST-ID we set here), which then triggers
        link_care_context() for this patient's unlinked care contexts.
        Gateway: POST /api/hiecm/v3/token/generate-token
        """
        if not (patient.abha_address or patient.abha_number):
            return {}

        from hms.models import ABDMLinkToken

        request_id = str(uuid.uuid4())
        gender_map = {"Male": "M", "Female": "F", "Other": "O"}

        payload = {"name": patient.full_name or ""}
        if patient.abha_address:
            payload["abhaAddress"] = patient.abha_address
        if patient.abha_number:
            payload["abhaNumber"] = patient.abha_number
        if patient.gender:
            payload["gender"] = gender_map.get(patient.gender, "O")
        if patient.date_of_birth:
            payload["yearOfBirth"] = patient.date_of_birth.year

        ABDMLinkToken.objects.create(
            patient      = patient,
            abha_address = patient.abha_address or "",
            request_id   = request_id,
        )
        headers = {
            "X-HIP-ID":   settings.ABDM_HIP_ID or "",
            "REQUEST-ID": request_id,
        }
        try:
            abdm.gateway_post("/api/hiecm/v3/token/generate-token", payload,
                              extra_headers=headers)
        except Exception as e:
            print(f"[HIP] generate_link_token failed: {e}")
        return {"requestId": request_id}

    @staticmethod
    def link_care_context(patient, x_link_token: str, contexts) -> dict:
        """
        Step 2 of HIP-initiated linking — link one or more not-yet-linked
        care contexts to the patient's ABHA address using a freshly issued
        link token. `contexts` is an iterable of ABDMCareContext rows for
        this patient, grouped here by hi_type per the spec's payload shape
        (one "patient[]" entry per hiType group).
        Gateway: POST /api/hiecm/hip/v3/link/carecontext

        Stamps pending_request_id on each context so the on_carecontext
        callback can confirm (-> linked=True) or leave it for retry.
        """
        from hms.models import ABDMCareContext

        contexts = list(contexts)
        if not contexts:
            return {}

        by_hi_type = {}
        for ctx in contexts:
            by_hi_type.setdefault(ctx.hi_type, []).append(ctx)

        patient_entries = [
            {
                "referenceNumber": f"{patient.id}-{hi_type}",
                "display":         patient.full_name,
                "careContexts": [
                    {"referenceNumber": c.reference_number, "display": c.display}
                    for c in ctx_list
                ],
                "hiType": hi_type,
                "count":  len(ctx_list),
            }
            for hi_type, ctx_list in by_hi_type.items()
        ]

        payload = {"patient": patient_entries}
        if patient.abha_address:
            payload["abhaAddress"] = patient.abha_address
        if patient.abha_number:
            payload["abhaNumber"] = patient.abha_number

        request_id = str(uuid.uuid4())
        headers = {
            "X-HIP-ID":     settings.ABDM_HIP_ID or "",
            "X-LINK-TOKEN": x_link_token,
            "REQUEST-ID":   request_id,
        }
        ABDMCareContext.objects.filter(
            id__in=[c.id for c in contexts]
        ).update(pending_request_id=request_id)

        try:
            return abdm.gateway_post("/api/hiecm/hip/v3/link/carecontext",
                                     payload, extra_headers=headers)
        except Exception as e:
            print(f"[HIP] link_care_context failed: {e}")
            return {}

    # ── Mobile Notification (no ABHA address) ───────────

    @staticmethod
    def notify_via_sms(patient_mobile: str, hip_id: str = None) -> dict:
        """
        Notify patient via SMS that a health record is available to fetch
        (used when the patient has no ABHA address on file).
        Gateway: POST /api/hiecm/hip/v3/link/patient/links/sms/notify2
        """
        payload = {
            "requestId": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "notification": {
                "phoneNo": patient_mobile,
                "hip": {
                    "id":   hip_id or settings.ABDM_HIP_ID or "",
                    "name": "Shradha Hospital",
                },
            }
        }
        try:
            return abdm.gateway_post(
                "/api/hiecm/hip/v3/link/patient/links/sms/notify2", payload
            )
        except Exception as e:
            print(f"[HIP] SMS notify failed: {e}")
            return {}

    # ── Data-Transfer Status Notify (M2 doc §6.3.6) ──────

    @staticmethod
    def notify_transfer_status(consent_id: str, transaction_id: str,
                               session_status: str, status_responses: list) -> dict:
        """
        Report the status of a health-data transfer to the HIE-CM Gateway,
        after actually pushing (or failing to push) data to the HIU's
        dataPushUrl. Call this from the data-flow request handler, not
        from record-save hooks (those use notify_care_context_update).
        Gateway: POST /api/hiecm/data-flow/v3/health-information/notify
        session_status: "TRANSFERRED" | "FAILED"
        status_responses: [{"careContextReference": ..., "hiStatus": "DELIVERED"|"ERRORED", "description": ...}]
        """
        payload = {
            "notification": {
                "consentId":     consent_id,
                "transactionId": transaction_id,
                "doneAt":        datetime.now(timezone.utc).isoformat(),
                "notifier": {
                    "type": "HIP",
                    "id":   settings.ABDM_HIP_ID or "",
                },
                "statusNotification": {
                    "sessionStatus":   session_status,
                    "hipId":           settings.ABDM_HIP_ID or "",
                    "statusResponses": status_responses,
                }
            }
        }
        try:
            return abdm.gateway_post(
                "/api/hiecm/data-flow/v3/health-information/notify", payload
            )
        except Exception as e:
            print(f"[HIP] Transfer status notify failed: {e}")
            return {}

    # ── User-Initiated Linking (M2 doc §5) ────────────────
    # A separate flow from HIP-initiated linking above: here the PATIENT
    # starts from a PHR app, and HIE-CM calls us (via views.py callbacks)
    # to discover/init/confirm the link.

    @staticmethod
    def find_patient_by_abha(abha_number: str = None, abha_address: str = None):
        """
        Patient.abha_number/abha_address are EncryptedCharField (Fernet --
        non-deterministic: the same plaintext encrypts to different
        ciphertext every save), so `.filter(abha_number=...)` / `.get(...)`
        compares plaintext against stored ciphertext and can NEVER match --
        not a corner case, it always returns nothing. Until a deterministic
        lookup column (e.g. an HMAC-hash index) is added, fall back to a
        full scan + in-Python decrypt-compare (acceptable at hospital-scale
        patient counts; would need indexing at real scale).
        """
        from hms.models import Patient
        if abha_number:
            for p in Patient.objects.all().only("id", "abha_number"):
                if p.abha_number == abha_number:
                    return p
        if abha_address:
            for p in Patient.objects.all().only("id", "abha_address"):
                if p.abha_address == abha_address:
                    return p
        return None

    @staticmethod
    def respond_to_discovery(request_id: str, transaction_id: str,
                              patient, matched_by: list) -> dict:
        """
        Our response to a patient-initiated discovery request (§5.3.3),
        listing this patient's known care contexts grouped by hiType.
        Gateway: POST /api/hiecm/user-initiated-linking/v3/patient/care-context/on-discover
        """
        from hms.models import ABDMCareContext
        contexts = ABDMCareContext.objects.filter(patient=patient)

        if not contexts.exists():
            payload = {
                "transactionId": transaction_id,
                "error": {"code": "ABDM-1010", "message": "Patient not found"},
                "response": {"requestId": request_id},
            }
        else:
            by_hi_type = {}
            for ctx in contexts:
                by_hi_type.setdefault(ctx.hi_type, []).append(ctx)
            payload = {
                "transactionId": transaction_id,
                "patient": [
                    {
                        "referenceNumber": f"{patient.id}-{hi_type}",
                        "display":         patient.full_name,
                        "careContexts": [
                            {"referenceNumber": c.reference_number, "display": c.display}
                            for c in ctx_list
                        ],
                        "hiType": hi_type,
                        "count":  len(ctx_list),
                    }
                    for hi_type, ctx_list in by_hi_type.items()
                ],
                "matchedBy": matched_by,
                "response": {"requestId": request_id},
            }
        try:
            return abdm.gateway_post(
                "/api/hiecm/user-initiated-linking/v3/patient/care-context/on-discover",
                payload,
            )
        except Exception as e:
            print(f"[HIP] Discovery response failed: {e}")
            return {}

    @staticmethod
    def gateway_post_on_discover_not_found(request_id: str, transaction_id: str) -> dict:
        """Same on-discover endpoint as above, for the no-match case."""
        payload = {
            "transactionId": transaction_id,
            "error": {"code": "ABDM-1010", "message": "Patient not found"},
            "response": {"requestId": request_id},
        }
        try:
            return abdm.gateway_post(
                "/api/hiecm/user-initiated-linking/v3/patient/care-context/on-discover",
                payload,
            )
        except Exception as e:
            print(f"[HIP] Discovery not-found response failed: {e}")
            return {}

    @staticmethod
    def respond_to_link_init(request_id: str, transaction_id: str, patient) -> dict:
        """
        Our response to a patient-initiated link-init request (§5.3.7).
        Generates our own link reference + a fresh OTP that the patient
        must enter on ABDM's PHR app (relayed back to us via the confirm
        callback), and delivers that OTP over WhatsApp (this project has
        no SMS gateway, but does have a working WhatsApp Business
        integration -- see hms/services/whatsapp.py's
        send_authentication_otp and the approved 'abdm_linking_otp'
        AUTHENTICATION-category template). If WhatsApp delivery fails
        (unreachable number, API error), the OTP is still logged so
        sandbox testing can proceed with manual relay.
        Gateway: POST /api/hiecm/user-initiated-linking/v3/link/care-context/on-init
        """
        from hms.models import ABDMLinkingSession
        from hms.services.whatsapp import send_authentication_otp, normalize_indian_mobile, WhatsAppSendError

        link_reference = str(uuid.uuid4())
        otp = f"{random.randint(0, 999999):06d}"
        ABDMLinkingSession.objects.create(
            transaction_id = transaction_id,
            link_reference = link_reference,
            patient        = patient,
            otp            = otp,
        )

        whatsapp_to = normalize_indian_mobile(patient.mobile_no)
        if whatsapp_to:
            try:
                send_authentication_otp(whatsapp_to, otp)
            except WhatsAppSendError as e:
                print(f"[HIP] User-initiated-linking OTP WhatsApp delivery failed for "
                      f"patient {patient.id}: {e}  [otp={otp}, deliver manually]")
        else:
            print(f"[HIP] User-initiated-linking OTP for patient {patient.id}: {otp} "
                  f"[no usable mobile number, deliver manually]")

        payload = {
            "transactionId": transaction_id,
            "link": {
                "referenceNumber":    link_reference,
                "authenticationType": "DIRECT",
                "meta": {
                    "communicationMedium": "MOBILE",
                    "communicationHint":   "OTP",
                    "communicationExpiry": (datetime.now(timezone.utc)
                                            + timedelta(minutes=10)).isoformat(),
                }
            },
            "response": {"requestId": request_id},
        }
        try:
            return abdm.gateway_post(
                "/api/hiecm/user-initiated-linking/v3/link/care-context/on-init",
                payload,
            )
        except Exception as e:
            print(f"[HIP] Link-init response failed: {e}")
            return {}

    @staticmethod
    def respond_to_link_confirm(request_id: str, session) -> dict:
        """
        Our response confirming a patient-entered OTP for user-initiated
        linking (§5.3.11). `session` is the ABDMLinkingSession matched by
        linkRefNumber; the caller has already verified session.otp and
        marks session.confirmed_at before calling this.
        Gateway: POST /api/hiecm/user-initiated-linking/v3/link/care-context/on-confirm
        """
        from hms.models import ABDMCareContext
        contexts = ABDMCareContext.objects.filter(patient=session.patient)
        by_hi_type = {}
        for ctx in contexts:
            by_hi_type.setdefault(ctx.hi_type, []).append(ctx)

        payload = {
            "patient": [
                {
                    "referenceNumber": session.link_reference,
                    "display":         session.patient.full_name,
                    "careContexts": [
                        {"referenceNumber": c.reference_number, "display": c.display}
                        for c in ctx_list
                    ],
                    "hiType": hi_type,
                    "count":  len(ctx_list),
                }
                for hi_type, ctx_list in by_hi_type.items()
            ],
            "response": {"requestId": request_id},
        }
        try:
            return abdm.gateway_post(
                "/api/hiecm/user-initiated-linking/v3/link/care-context/on-confirm",
                payload,
            )
        except Exception as e:
            print(f"[HIP] Link-confirm response failed: {e}")
            return {}

    # ── Consent Storage ──────────────────────────────────

    @staticmethod
    def store_consent(consent_id: str, consent_artifact: dict) -> None:
        """
        Store consent artifact (M2 doc §6.3.1's flat payload -- "patient"
        is the ABHA address string directly, not a nested {id: ...} dict).
        Consent must be verified before sharing health data.
        """
        from hms.models import ABDMConsent
        permission = consent_artifact.get("permission", {})
        ABDMConsent.objects.update_or_create(
            consent_id=consent_id,
            defaults={
                "artifact":     json.dumps(consent_artifact),
                "status":       consent_artifact.get("status", "GRANTED"),
                "patient_abha": consent_artifact.get("patient", ""),
                "hi_types":     json.dumps(consent_artifact.get("hiTypes", [])),
                "date_from":    permission.get("dateRange", {}).get("from", ""),
                "date_to":      permission.get("dateRange", {}).get("to", ""),
                "expire_at":    permission.get("dataEraseAt", ""),
            }
        )

    @staticmethod
    def ack_consent_notify(request_id: str, consent_id: str,
                           status: str = "OK", error: dict = None) -> dict:
        """
        Ack the consent-approved/revoked callback (§6.3.2) -- required
        separately from the HTTP 202 already returned to that callback.
        Gateway: POST /api/hiecm/consent/v3/request/hip/on-notify
        """
        payload = {
            "acknowledgement": {"status": status, "consentId": consent_id},
            "response": {"requestId": request_id},
        }
        if error:
            payload["error"] = error
        try:
            return abdm.gateway_post(
                "/api/hiecm/consent/v3/request/hip/on-notify", payload
            )
        except Exception as e:
            print(f"[HIP] Consent-notify ack failed for {consent_id}: {e}")
            return {}

    @staticmethod
    def ack_health_info_request(request_id: str, transaction_id: str,
                                session_status: str = "ACKNOWLEDGED",
                                error: dict = None) -> dict:
        """
        Ack the health-information-request callback (§6.3.4) -- required
        separately from the HTTP 202 already returned to that callback.
        Gateway: POST /api/hiecm/data-flow/v3/health-information/hip/on-request
        """
        payload = {"response": {"requestId": request_id}}
        if error:
            payload["error"] = error
        else:
            payload["hiRequest"] = {
                "transactionId": transaction_id,
                "sessionStatus": session_status,
            }
        try:
            return abdm.gateway_post(
                "/api/hiecm/data-flow/v3/health-information/hip/on-request", payload
            )
        except Exception as e:
            print(f"[HIP] Health-info-request ack failed: {e}")
            return {}

    # ── Health Data Packaging ────────────────────────────

    @staticmethod
    def generate_ecdh_keypair():
        """
        Generate our (HIP) ephemeral BC25519 key pair + nonce for one
        data-push transaction, per ABDM's Fidelius keyMaterial protocol
        (§6.3.3-6.3.5). Must be generated ONCE per transaction, before
        packaging any entries -- the same key pair is used both to
        encrypt every entry (package_health_data) and to populate the
        outgoing keyMaterial the HIU needs to derive the matching key
        (transfer_health_data), so encryption and the advertised key
        can't drift apart.
        Returns (private_key_b64, public_key_x509_b64, nonce_b64).
        """
        return fidelius.generate_key_material()

    @staticmethod
    def package_health_data(fhir_bundle: dict, care_context_ref: str,
                            sender_private_key_b64: str, sender_nonce_b64: str,
                            requester_public_key_b64: str, requester_nonce_b64: str) -> dict:
        """
        Package one FHIR bundle as one "entries[]" item for the data push
        (M2 doc §6.3.5), AES-256-GCM encrypted per ABDM's Fidelius protocol
        (see hms/abdm/services/fidelius.py for the full construction).

        `sender_*` is this HIP's own key material for this transaction
        (from generate_ecdh_keypair, called once before packaging any
        entries); `requester_*` is the HIU's key material, as given in
        the health-information request's hiRequest.keyMaterial.
        """
        bundle_json = json.dumps(fhir_bundle)
        content_b64 = fidelius.encrypt_content(
            bundle_json,
            sender_private_key_b64    = sender_private_key_b64,
            sender_nonce_b64          = sender_nonce_b64,
            requester_public_key_b64  = requester_public_key_b64,
            requester_nonce_b64       = requester_nonce_b64,
        )
        return {
            "content":             content_b64,
            "media":               "application/fhir+json",
            # Checksum of the PLAINTEXT bundle -- lets the HIU verify
            # integrity of what it gets back after decrypting, not of
            # the ciphertext itself.
            "checksum":            hashlib.sha256(bundle_json.encode()).hexdigest(),
            "careContextReference": care_context_ref,
        }

    # ── Health Data Transfer ─────────────────────────────

    @staticmethod
    def transfer_health_data(transaction_id: str, data_push_url: str, entries: list,
                             sender_public_key_x509_b64: str, sender_nonce_b64: str) -> dict:
        """
        Push packaged entries (see package_health_data) to the HIU's
        dataPushUrl (§6.3.5), advertising the SAME key pair + nonce
        (from generate_ecdh_keypair) that was used to encrypt those
        entries, so the HIU can derive the matching AES key.
        """
        payload = {
            "pageNumber":    1,
            "pageCount":     1,
            "transactionId": transaction_id,
            "entries":       entries,
            "keyMaterial": {
                "cryptoAlg": "ECDH",
                "curve":     "Curve25519",
                "dhPublicKey": {
                    "expiry":     (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                    "parameters": "Curve25519/32byte random key",
                    "keyValue":   sender_public_key_x509_b64,
                },
                "nonce": sender_nonce_b64,
            },
        }
        try:
            r = requests.post(
                data_push_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            r.raise_for_status()
            return {"status": "transferred"}
        except Exception as e:
            print(f"[HIP] Data transfer failed: {e}")
            return {"status": "failed", "error": str(e)}


    # ── Care Context Update Notification ─────────────────

    @staticmethod
    def notify_care_context_update(patient, patient_reference: str,
                                   care_context_ref: str, hi_type: str) -> dict:
        """
        Notify the HIE-CM Gateway that a new/updated health record is
        available for a care context already linked to the patient's
        ABHA address. Call this after saving an OPD consultation,
        discharge summary, or lab/USG report.

        Gateway: POST /api/hiecm/hip/v3/link/context/notify
        hi_type: one of "OPConsultation", "DischargeSummary", "DiagnosticReport"

        Expects 202 Accepted — the gateway's actual acknowledgement of
        this notification arrives asynchronously at the on-notify callback.

        Skips silently (returns {}) if the patient has no verified ABHA
        address linked — there is no care context to notify against.
        """
        if not (patient and patient.abha_address and patient.abha_verified):
            return {}

        payload = {
            "notification": {
                "patient": {
                    "id": patient.abha_address,
                },
                "careContext": {
                    "patientReference":     patient_reference,
                    "careContextReference": care_context_ref,
                },
                "hiTypes": [hi_type],
                "date":    datetime.now(timezone.utc).isoformat(),
                "hip": {
                    "id": settings.ABDM_HIP_ID or "",
                },
            }
        }
        headers      = abdm._headers({"X-HIP-ID": settings.ABDM_HIP_ID or ""})
        gateway_base = settings.ABDM_GATEWAY_URL.rstrip("/")
        try:
            r = requests.post(
                f"{gateway_base}/api/hiecm/hip/v3/link/context/notify",
                json=payload,
                headers=headers,
                timeout=20,
            )
            if r.status_code != 202:
                print(f"[HIP] Care context notify for {care_context_ref} "
                      f"got HTTP {r.status_code}: {r.text[:300]}")
            r.raise_for_status()
            return r.json() if r.content else {}
        except Exception as e:
            print(f"[HIP] Care context notify failed for {care_context_ref}: {e}")
            return {}

    @staticmethod
    def notify_opd_consultation(consultation) -> dict:
        """Link (first time) or notify-update (already linked) an OPD consultation record."""
        patient = consultation.appointment.patient
        return HIPService.ensure_care_context_linked(
            patient          = patient,
            reference_number = f"CON-{consultation.id}",
            display          = f"OPD – {consultation.appointment.date}",
            hi_type          = "OPConsultation",
        )

    @staticmethod
    def notify_discharge_summary(admission) -> dict:
        """Link (first time) or notify-update (already linked) a discharge summary."""
        patient = admission.patient
        return HIPService.ensure_care_context_linked(
            patient          = patient,
            reference_number = f"IPD-{admission.id}",
            display          = f"Discharge Summary – {admission.ipd_no or admission.id}",
            hi_type          = "DischargeSummary",
        )

    @staticmethod
    def notify_lab_report(bill_item) -> dict:
        """Link (first time) or notify-update (already linked) a lab report."""
        patient = bill_item.bill.patient
        return HIPService.ensure_care_context_linked(
            patient          = patient,
            reference_number = f"LAB-{bill_item.id}",
            display          = f"Lab: {bill_item.investigation.name}",
            hi_type          = "DiagnosticReport",
        )

    @staticmethod
    def notify_usg_report(report) -> dict:
        """Link (first time) or notify-update (already linked) a USG report."""
        patient = report.patient
        return HIPService.ensure_care_context_linked(
            patient          = patient,
            reference_number = f"USG-{report.id}",
            display          = f"USG: {report.get_scan_type_display()}",
            hi_type          = "DiagnosticReport",
        )