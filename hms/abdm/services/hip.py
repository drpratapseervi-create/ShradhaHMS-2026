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
from datetime import datetime, timezone
from django.conf import settings
from django.db import models

from .auth import abdm


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

    # ── HIP Initiated Linking ────────────────────────────

    @staticmethod
    def add_care_context(patient_abha: str, care_context_ref: str,
                         care_context_display: str) -> dict:
        """
        HIP-initiated linking of care context to HIE-CM.
        Called after creating OPD/Lab/Discharge record.
        Gateway: POST /v0.5/links/link/add-contexts
        """
        payload = {
            "requestId": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "link": {
                "accessToken":  HIPService._get_link_token(patient_abha),
                "patient": {
                    "referenceNumber": patient_abha,
                    "careContexts": [
                        {
                            "referenceNumber": care_context_ref,
                            "display":         care_context_display,
                        }
                    ]
                }
            }
        }
        try:
            return abdm.post("/v0.5/links/link/add-contexts", payload)
        except Exception as e:
            print(f"[HIP] Care context link failed: {e}")
            return {}

    @staticmethod
    def _get_link_token(patient_abha: str) -> str:
        """
        Get a link token from ABDM for HIP-initiated linking.
        In production this comes from the patient's ABHA session.
        For now returns a placeholder — will work once M1 is live.
        """
        return "LINK_TOKEN_FROM_PATIENT_SESSION"

    # ── Mobile Notification (no ABHA address) ───────────

    @staticmethod
    def notify_via_sms(patient_mobile: str, hip_id: str,
                       care_context_ref: str) -> dict:
        """
        Notify patient via SMS when no ABHA address available.
        Gateway: POST /v0.5/patients/sms/notify2
        """
        payload = {
            "requestId":  str(uuid.uuid4()),
            "timestamp":  datetime.now(timezone.utc).isoformat(),
            "notification": {
                "phoneNo":   f"+91{patient_mobile}",
                "hip": {
                    "name": "Shradha Hospital",
                    "id":   hip_id or settings.ABDM_HIP_ID,
                },
                "careContextInfo": [
                    {"careContextReference": care_context_ref}
                ],
                "hiTypes": ["OPDischargeNote"],
                "date":    datetime.now(timezone.utc).date().isoformat(),
            }
        }
        try:
            return abdm.post("/v0.5/patients/sms/notify2", payload)
        except Exception as e:
            print(f"[HIP] SMS notify failed: {e}")
            return {}

    # ── Notify Health Record Ready ───────────────────────

    @staticmethod
    def notify_health_record_ready(patient_abha: str, care_context_ref: str,
                                   hi_type: str = "OPDischargeNote") -> dict:
        """
        Notify HIE-CM that new health record is available.
        Gateway: POST /v0.5/health-information/notify
        """
        payload = {
            "requestId": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "notification": {
                "consentId":  "",
                "doneAt":     datetime.now(timezone.utc).isoformat(),
                "notifier": {
                    "type": "HIP",
                    "id":   settings.ABDM_HIP_ID or "",
                },
                "statusNotification": {
                    "sessionStatus": "TRANSFERRED",
                    "hipId":         settings.ABDM_HIP_ID or "",
                    "statusResponses": [
                        {
                            "careContextReference": care_context_ref,
                            "hiStatus":            "OK",
                            "description":         f"{hi_type} available",
                        }
                    ]
                }
            }
        }
        try:
            return abdm.post("/v0.5/health-information/notify", payload)
        except Exception as e:
            print(f"[HIP] Notify failed: {e}")
            return {}

    # ── Discovery Response ───────────────────────────────

    @staticmethod
    def respond_to_discovery(request_id: str, transaction_id: str,
                              patient, care_contexts: list) -> dict:
        """
        Respond to patient-initiated discovery request.
        Called from abdm_on_discover callback view.
        Gateway: POST /v0.5/care-contexts/on-discover
        """
        payload = {
            "requestId":     str(uuid.uuid4()),
            "timestamp":     datetime.now(timezone.utc).isoformat(),
            "transactionId": transaction_id,
            "patient": {
                "referenceNumber": patient.uhid,
                "display":         patient.full_name,
                "careContexts": [
                    {
                        "referenceNumber": cc["ref"],
                        "display":         cc["display"],
                    }
                    for cc in care_contexts
                ],
                "matchedBy": ["MOBILE", "MR"],
            },
            "resp": {"requestId": request_id}
        }
        try:
            return abdm.post("/v0.5/care-contexts/on-discover", payload)
        except Exception as e:
            print(f"[HIP] Discovery response failed: {e}")
            return {}

    # ── Consent Storage ──────────────────────────────────

    @staticmethod
    def store_consent(consent_id: str, consent_artifact: dict) -> None:
        """
        Store consent artifact in database.
        Consent must be verified before sharing health data.
        """
        from hms.models import ABDMConsent
        ABDMConsent.objects.update_or_create(
            consent_id=consent_id,
            defaults={
                "artifact":     json.dumps(consent_artifact),
                "status":       consent_artifact.get("status", "GRANTED"),
                "patient_abha": consent_artifact.get("patient", {}).get("id", ""),
                "hi_types":     json.dumps(consent_artifact.get("hiTypes", [])),
                "date_from":    consent_artifact.get("permission", {}).get("dateRange", {}).get("from", ""),
                "date_to":      consent_artifact.get("permission", {}).get("dateRange", {}).get("to", ""),
                "expire_at":    consent_artifact.get("permission", {}).get("dataEraseAt", ""),
            }
        )

    @staticmethod
    def verify_consent(consent_id: str, hi_type: str) -> bool:
        """
        Verify a consent is valid before sharing health data.
        Returns True if consent is GRANTED and hi_type is allowed.
        """
        try:
            from hms.models import ABDMConsent
            consent = ABDMConsent.objects.get(consent_id=consent_id)
            if consent.status != "GRANTED":
                return False
            hi_types = json.loads(consent.hi_types or "[]")
            return hi_type in hi_types or not hi_types
        except Exception:
            return False

    # ── Health Data Packaging ────────────────────────────

    @staticmethod
    def package_health_data(fhir_bundle: dict,
                            key_material: dict) -> dict:
        """
        Encrypt FHIR bundle for transfer to HIU.
        Uses ECDH key exchange as required by ABDM.
        key_material: from consent request (HIU's public key)

        Note: Full ECDH encryption requires the fidelius library.
        In production, install: pip install fidelius (Linux only)
        For now returns base64-encoded JSON as placeholder.
        """
        bundle_json    = json.dumps(fhir_bundle).encode()
        bundle_b64     = base64.b64encode(bundle_json).decode()

        # TODO: Replace with actual ECDH encryption using fidelius
        # from fidelius import Fidelius
        # encrypted = Fidelius.encrypt(bundle_json, key_material)

        return {
            "content":          bundle_b64,
            "media":            "application/fhir+json",
            "checksum":         hashlib.md5(bundle_json).hexdigest(),
            "careContextReference": "",
        }

    # ── Health Data Transfer ─────────────────────────────

    @staticmethod
    def transfer_health_data(transaction_id: str, consent_id: str,
                             data_push_url: str, entries: list,
                             key_material: dict) -> dict:
        """
        Transfer packaged health data to HIU data push URL.
        Called after consent verification.
        """
        payload = {
            "pageNumber":   1,
            "pageCount":    1,
            "transactionId": transaction_id,
            "entries":      entries,
            "keyMaterial":  key_material,
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

    # ── Link Confirm Response ────────────────────────────

    @staticmethod
    def on_link_confirm(request_id: str, patient_ref: str,
                        care_contexts: list) -> dict:
        """
        Confirm care context linking after OTP verification.
        Gateway: POST /v0.5/links/link/on-confirm
        """
        payload = {
            "requestId": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "patient": {
                "referenceNumber": patient_ref,
                "display":         patient_ref,
                "careContexts":    care_contexts,
            },
            "resp": {"requestId": request_id}
        }
        try:
            return abdm.post("/v0.5/links/link/on-confirm", payload)
        except Exception as e:
            print(f"[HIP] Link confirm failed: {e}")
            return {}