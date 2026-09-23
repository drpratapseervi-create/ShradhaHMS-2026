"""
ABDM M3 -- Health Information User (HIU) services: this hospital acting
as a REQUESTER of a patient's records held by other ABDM-connected
facilities (the mirror role of HIPService, which shares OUR records).

Reference: "SANDBOX DOCUMENTATION (ABDM_Milestone 3)" -- §4 (consent
flow: request/init, on-init, notify, on-notify ack, fetch, on-fetch) and
§5 (data flow: health-information/request, on-request, the data push we
receive, notify). All calls go through the same HIE-CM gateway
(hms/abdm/services/auth.py's `abdm`) used by HIPService, under
/api/hiecm/... paths.

Backend/service-layer only for now -- no doctor-facing UI yet.
"""

import uuid
import json
from datetime import datetime, timezone, timedelta

from django.conf import settings

from .auth import abdm
from . import fidelius


DATA_PUSH_PATH = "/api/v3/hiu/health-information/transfer/"


class HIUService:

    # ── Consent Request (M3 doc §4.3.1) ──────────────────

    @staticmethod
    def request_consent(patient, hi_types, date_from, date_to,
                        requester_name, requester_id_type, requester_id_value,
                        requester_id_system, purpose_code="CAREMGT",
                        purpose_text="Care Management", purpose_ref_uri="",
                        hip_id=""):
        """
        Initiate a consent request to view `patient`'s records held by
        (optionally) a specific HIP, or any HIP if hip_id is blank. The
        consent request id itself is NOT returned here -- it arrives
        later via the on-init callback, matched by our own REQUEST-ID.
        Gateway: POST /api/hiecm/consent/v3/request/init
        Returns the ABDMConsentRequest row just created.
        """
        from hms.models import ABDMConsentRequest

        if not patient.abha_address:
            raise ValueError(f"Patient {patient.id} has no ABHA address on file")

        request_id = str(uuid.uuid4())

        consent_request = ABDMConsentRequest.objects.create(
            patient             = patient,
            hip_id              = hip_id,
            purpose_code        = purpose_code,
            purpose_text        = purpose_text,
            hi_types            = hi_types,
            date_from           = date_from,
            date_to             = date_to,
            requester_name      = requester_name,
            requester_id_type   = requester_id_type,
            requester_id_value  = requester_id_value,
            requester_id_system = requester_id_system,
            request_id          = request_id,
        )

        consent_payload = {
            "purpose": {"text": purpose_text, "code": purpose_code, "refUri": purpose_ref_uri},
            "patient": {"id": patient.abha_address},
            "hiu": {"id": settings.ABDM_HIU_ID},
            "requester": {
                "name": requester_name,
                "identifier": {
                    "type":   requester_id_type,
                    "value":  requester_id_value,
                    "system": requester_id_system,
                },
            },
            "hiTypes": hi_types,
            "permission": {
                "accessMode": "VIEW",
                "dateRange": {"from": date_from.isoformat(), "to": date_to.isoformat()},
                "dataEraseAt": (date_to + timedelta(days=365)).isoformat(),
                "frequency": {"unit": "DAY", "value": 1, "repeats": 0},
            },
        }
        if hip_id:
            consent_payload["hip"] = {"id": hip_id}

        try:
            abdm.gateway_post(
                "/api/hiecm/consent/v3/request/init",
                {"consent": consent_payload},
                extra_headers={"REQUEST-ID": request_id},
            )
        except Exception as e:
            print(f"[HIU] request_consent failed for patient {patient.id}: {e}")

        return consent_request

    @staticmethod
    def record_consent_request_ack(request_id: str, consent_request_id: str = None, error: dict = None):
        """
        Handle the on-init callback (§4.3.2) -- fills in consent_request_id
        on the ABDMConsentRequest matched by our own request_id (sent as
        the REQUEST-ID header on request_consent's call, echoed back here
        as response.requestId).
        """
        from hms.models import ABDMConsentRequest

        consent_request = ABDMConsentRequest.objects.filter(request_id=request_id).first()
        if not consent_request:
            print(f"[HIU] on-init: no ABDMConsentRequest for request_id={request_id}")
            return
        if error:
            print(f"[HIU] on-init error for request_id={request_id}: {error}")
            return
        consent_request.consent_request_id = consent_request_id or ""
        consent_request.save(update_fields=["consent_request_id"])

    # ── Consent Notify + Ack (M3 doc §4.3.3/§4.3.4) ──────

    @staticmethod
    def ack_consent_notify(response_request_id: str, consent_ids: list, status: str = "OK", error: dict = None) -> dict:
        """
        Ack the consent-approved/denied/revoked notify callback (§4.3.3) --
        required separately from the HTTP 202 already returned to that
        callback. `consent_ids` is every consentArtefact id from that
        notify payload (a patient can grant multiple HIPs in one notify).
        Gateway: POST /api/hiecm/consent/v3/request/hiu/on-notify
        """
        payload = {
            "acknowledgement": [{"status": status, "consentId": cid} for cid in consent_ids],
            "error": error,
            "response": {"requestId": response_request_id},
        }
        try:
            return abdm.gateway_post("/api/hiecm/consent/v3/request/hiu/on-notify", payload)
        except Exception as e:
            print(f"[HIU] Consent-notify ack failed for {consent_ids}: {e}")
            return {}

    @staticmethod
    def record_consent_decision(consent_request_id: str, status: str, consent_ids: list):
        """
        Update the ABDMConsentRequest's status from the notify payload,
        and create a status="FETCHING" stub ABDMConsentArtefact for each
        granted consent id, ready for fetch_artefact() to fill in.
        """
        from hms.models import ABDMConsentRequest, ABDMConsentArtefact

        consent_request = ABDMConsentRequest.objects.filter(consent_request_id=consent_request_id).first()
        if not consent_request:
            print(f"[HIU] notify: no ABDMConsentRequest for consent_request_id={consent_request_id}")
            return []

        consent_request.status = status
        consent_request.save(update_fields=["status"])

        stubs = []
        if status == "GRANTED":
            for cid in consent_ids:
                stub, _ = ABDMConsentArtefact.objects.get_or_create(
                    consent_id=cid,
                    defaults={"consent_request": consent_request, "status": "FETCHING"},
                )
                stubs.append(stub)
        return stubs

    # ── Fetch Consent Artefact (M3 doc §4.3.7/§4.3.8) ────

    @staticmethod
    def fetch_artefact(consent_id: str):
        """
        Fetch the full consent artefact for a granted consent_id (already
        stubbed by record_consent_decision). The details themselves
        arrive later via the on-fetch callback, matched by consent_id.
        Gateway: POST /api/hiecm/consent/v3/fetch
        """
        try:
            abdm.gateway_post(
                "/api/hiecm/consent/v3/fetch",
                {"consentId": consent_id},
                extra_headers={"X-HIU-ID": settings.ABDM_HIU_ID or ""},
            )
        except Exception as e:
            print(f"[HIU] fetch_artefact failed for consent_id={consent_id}: {e}")

    @staticmethod
    def store_fetched_artefact(consent_data: dict):
        """
        Handle the on-fetch callback (§4.3.8) -- fills in the
        status="FETCHING" stub ABDMConsentArtefact created by
        record_consent_decision, matched by consent_id.
        `consent_data` is the incoming request's "consent" object.
        """
        from hms.models import ABDMConsentArtefact

        detail = consent_data.get("consentDetail", {})
        consent_id = detail.get("consentId")
        if not consent_id:
            print("[HIU] on-fetch: missing consentDetail.consentId")
            return

        permission = detail.get("permission", {})
        date_range = permission.get("dateRange", {})

        ABDMConsentArtefact.objects.filter(consent_id=consent_id).update(
            hip_id       = detail.get("hip", {}).get("id", ""),
            hi_types     = detail.get("hiTypes", []),
            date_from    = date_range.get("from") or None,
            date_to      = date_range.get("to") or None,
            status       = consent_data.get("status", "GRANTED"),
            raw_artefact = json.dumps(consent_data),
        )

    # ── Data Request (M3 doc §5.3.1/§5.3.2) ──────────────

    @staticmethod
    def request_health_information(consent_artefact, date_from=None, date_to=None):
        """
        Request the actual health data for a fetched consent artefact.
        Generates OUR OWN ephemeral Fidelius key material and stores it
        on the new ABDMHealthInformationRequest row -- needed later to
        decrypt the HIP's data push, which arrives asynchronously at our
        dataPushUrl. The transaction_id itself is NOT returned here --
        it arrives via the on-request callback, matched by our own
        REQUEST-ID.
        Gateway: POST /api/hiecm/data-flow/v3/health-information/request
        """
        from hms.models import ABDMHealthInformationRequest

        if not settings.ABDM_HIU_CALLBACK_BASE_URL:
            raise ValueError("ABDM_HIU_CALLBACK_BASE_URL is not configured -- "
                             "cannot build a dataPushUrl reachable from the ABDM sandbox")

        date_from = date_from or consent_artefact.date_from
        date_to   = date_to or consent_artefact.date_to

        our_private_key, our_public_key, our_nonce = fidelius.generate_key_material()
        request_id = str(uuid.uuid4())
        data_push_url = settings.ABDM_HIU_CALLBACK_BASE_URL.rstrip("/") + DATA_PUSH_PATH

        hi_request = ABDMHealthInformationRequest.objects.create(
            consent_artefact = consent_artefact,
            request_id       = request_id,
            our_private_key  = our_private_key,
            our_public_key   = our_public_key,
            our_nonce        = our_nonce,
        )

        payload = {
            "hiRequest": {
                "consent": {"id": consent_artefact.consent_id},
                "dateRange": {"from": date_from.isoformat(), "to": date_to.isoformat()},
                "dataPushUrl": data_push_url,
                "keyMaterial": {
                    "cryptoAlg": "ECDH",
                    "curve": "Curve25519",
                    "dhPublicKey": {
                        "expiry":     (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                        "parameters": "Curve25519/32byte random key",
                        "keyValue":   our_public_key,
                    },
                    "nonce": our_nonce,
                },
            }
        }

        try:
            abdm.gateway_post(
                "/api/hiecm/data-flow/v3/health-information/request",
                payload,
                extra_headers={"REQUEST-ID": request_id, "X-HIU-ID": settings.ABDM_HIU_ID or ""},
            )
        except Exception as e:
            print(f"[HIU] request_health_information failed for consent_id="
                  f"{consent_artefact.consent_id}: {e}")

        return hi_request

    @staticmethod
    def record_health_information_ack(request_id: str, transaction_id: str = None, error: dict = None):
        """
        Handle the on-request callback (§5.3.2) -- fills in transaction_id
        on the ABDMHealthInformationRequest matched by our own request_id.
        No separate outbound ack call is required for this one (unlike
        the consent-notify ack) -- the caller just returns HTTP 200/202.
        """
        from hms.models import ABDMHealthInformationRequest

        hi_request = ABDMHealthInformationRequest.objects.filter(request_id=request_id).first()
        if not hi_request:
            print(f"[HIU] on-request: no ABDMHealthInformationRequest for request_id={request_id}")
            return
        if error:
            hi_request.status = "FAILED"
            hi_request.save(update_fields=["status"])
            print(f"[HIU] on-request error for request_id={request_id}: {error}")
            return
        hi_request.transaction_id = transaction_id
        hi_request.save(update_fields=["transaction_id"])

    # ── Receiving the Data Push (M3 doc §5.3.2's payload) ─

    @staticmethod
    def receive_data_push(transaction_id: str, entries: list, key_material: dict) -> list:
        """
        Handle the actual data push a HIP sends to our dataPushUrl --
        same payload shape HIPService.transfer_health_data sends, from
        the opposite side. Decrypts each entry with the HIP's key
        material (from this payload) + our own stored key material
        (from request_health_information), and stores one
        ABDMReceivedRecord per entry.

        Returns the list of {careContextReference, hiStatus} dicts for
        notify_received() to report back to the CM.
        """
        from hms.models import ABDMHealthInformationRequest, ABDMReceivedRecord

        hi_request = ABDMHealthInformationRequest.objects.filter(transaction_id=transaction_id).first()
        if not hi_request:
            print(f"[HIU] data push: no ABDMHealthInformationRequest for transaction_id={transaction_id}")
            return []

        hip_public_key = key_material.get("dhPublicKey", {}).get("keyValue")
        hip_nonce      = key_material.get("nonce")

        status_responses = []
        for entry in entries:
            care_context_ref = entry.get("careContextReference", "")
            try:
                plaintext = fidelius.decrypt_content(
                    entry["content"],
                    own_private_key_b64      = hi_request.our_private_key,
                    own_nonce_b64            = hi_request.our_nonce,
                    other_public_key_b64     = hip_public_key,
                    other_nonce_b64          = hip_nonce,
                )
                ABDMReceivedRecord.objects.create(
                    hi_request             = hi_request,
                    care_context_reference = care_context_ref,
                    hi_status              = "OK",
                    fhir_bundle            = plaintext,
                )
                status_responses.append({"careContextReference": care_context_ref, "hiStatus": "OK"})
            except Exception as e:
                print(f"[HIU] Failed to decrypt entry {care_context_ref}: {e}")
                ABDMReceivedRecord.objects.create(
                    hi_request             = hi_request,
                    care_context_reference = care_context_ref,
                    hi_status              = "ERRORED",
                    error_detail           = str(e)[:255],
                )
                status_responses.append({"careContextReference": care_context_ref, "hiStatus": "ERRORED"})

        hi_request.status = "RECEIVED" if all(s["hiStatus"] == "OK" for s in status_responses) else "FAILED"
        hi_request.save(update_fields=["status"])

        return status_responses

    # ── Notify (M3 doc §5.3.3) ────────────────────────────

    @staticmethod
    def notify_received(hi_request, status_responses: list) -> dict:
        """
        Tell the CM whether the data push was received successfully.
        Gateway: POST /api/hiecm/data-flow/v3/health-information/notify
        """
        session_status = "RECEIVED" if all(s["hiStatus"] == "OK" for s in status_responses) else "FAILED"
        payload = {
            "notification": {
                "consentId":     hi_request.consent_artefact.consent_id,
                "transactionId": hi_request.transaction_id,
                "doneAt":        datetime.now(timezone.utc).isoformat(),
                "notifier": {
                    "type": "HIU",
                    "id":   settings.ABDM_HIU_ID or "",
                },
                "statusNotification": {
                    "sessionStatus":    session_status,
                    "hipId":            hi_request.consent_artefact.hip_id,
                    "statusResponses":  status_responses,
                },
            }
        }
        try:
            return abdm.gateway_post("/api/hiecm/data-flow/v3/health-information/notify", payload)
        except Exception as e:
            print(f"[HIU] notify_received failed for transaction_id={hi_request.transaction_id}: {e}")
            return {}
