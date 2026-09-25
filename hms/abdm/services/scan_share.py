"""
ABDM Milestone 1 — Scan & Share (V3)
====================================
A patient scans the hospital's ABDM counter QR code in their ABHA/PHR app and
shares their verified profile. HIE-CM calls our bridge:

    POST /api/v3/hip/patient/share
    {intent: "PROFILE_SHARE",
     metaData: {hipId, context, hprId, latitude, longitude},
     profile: {patient: {abhaNumber, abhaAddress, name, gender,
                         dayOfBirth, monthOfBirth, yearOfBirth, phoneNumber,
                         address: {line, district, state, pincode}}}}

We match (or register) the Patient, issue a same-day queue token and reply:

    POST {gateway}/api/hiecm/patient-share/v3/on-share
    {acknowledgement: {status, abhaAddress, profile: {context, tokenNumber, expiry}},
     response: {requestId}}

Paths and payload shapes follow NHA's reference implementation
(github.com/NHA-ABDM/ABDM-wrapper, v3 ProfileShareV3Service), which also
re-issues the same token when the same ABHA address shares again at the same
counter while the previous token is still valid.
"""

import logging
from datetime import date, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .auth import abdm
from .hip import HIPService

logger = logging.getLogger(__name__)

ON_SHARE_PATH = "/api/hiecm/patient-share/v3/on-share"
TOKEN_VALIDITY_SECONDS = 1800

GENDER_MAP = {"M": "Male", "F": "Female", "O": "Other", "U": "Other", "T": "Other"}


class ScanShareService:

    @staticmethod
    def handle_share(request_id: str, hip_id: str, data: dict):
        """Process one profile share and send on-share. Returns the ABDMScanShare row (or None)."""
        meta = data.get("metaData") or {}
        p = ((data.get("profile") or {}).get("patient")) or {}
        hip_id = hip_id or meta.get("hipId") or settings.ABDM_HIP_ID or ""
        context = meta.get("context") or ""
        abha_address = p.get("abhaAddress") or ""

        if not abha_address:
            logger.warning("[ScanShare] share without abhaAddress, request %s", request_id)
            ScanShareService.send_on_share_error(request_id, hip_id, "abhaAddress missing")
            return None

        try:
            share = ScanShareService._record_share(request_id, hip_id, context, p)
        except Exception as e:
            logger.exception("[ScanShare] failed to record share: %s", e)
            ScanShareService.send_on_share_error(request_id, hip_id, "FAILURE at HIP")
            return None

        ScanShareService.send_on_share(share, request_id)
        return share

    # ── Token + patient ─────────────────────────────────

    @staticmethod
    @transaction.atomic
    def _record_share(request_id, hip_id, context, p):
        from hms.models import ABDMScanShare

        today = timezone.localdate()
        abha_address = p.get("abhaAddress")

        # Same ABHA at the same counter while the token is still valid -> same token
        # (abha_address is encrypted, so compare in Python over today's rows).
        valid_after = timezone.now() - timedelta(seconds=TOKEN_VALIDITY_SECONDS)
        for existing in ABDMScanShare.objects.filter(
            token_date=today, context=context, created_at__gte=valid_after
        ):
            if existing.abha_address == abha_address:
                return existing

        todays = ABDMScanShare.objects.select_for_update().filter(token_date=today)
        next_token = max((int(s.token_number) for s in todays if s.token_number.isdigit()), default=0) + 1

        address = p.get("address") or {}
        share = ABDMScanShare(
            request_id=request_id,
            hip_id=hip_id,
            context=context,
            abha_number=p.get("abhaNumber") or "",
            abha_address=abha_address,
            name=(p.get("name") or "").strip(),
            gender=p.get("gender") or "",
            year_of_birth=str(p.get("yearOfBirth") or ""),
            month_of_birth=str(p.get("monthOfBirth") or ""),
            day_of_birth=str(p.get("dayOfBirth") or ""),
            phone_number=p.get("phoneNumber") or "",
            address_line=address.get("line") or "",
            district=address.get("district") or "",
            state=address.get("state") or "",
            pincode=address.get("pincode") or "",
            token_number=str(next_token),
            token_date=today,
        )
        share.patient, share.patient_created = ScanShareService._match_or_create_patient(share)
        share.save()
        return share

    @staticmethod
    def _match_or_create_patient(share):
        """Find the patient by ABHA; otherwise register them from the ABHA-verified profile."""
        from hms.models import Patient

        patient = HIPService.find_patient_by_abha(
            abha_number=share.abha_number or None,
            abha_address=share.abha_address or None,
        )
        if patient:
            changed = False
            if not patient.abha_number and share.abha_number:
                patient.abha_number = share.abha_number
                changed = True
            if not patient.abha_address and share.abha_address:
                patient.abha_address = share.abha_address
                changed = True
            if not patient.abha_verified:
                patient.abha_verified = True
                changed = True
            if changed:
                patient.save()
            return patient, False

        dob, age_years = ScanShareService._dob(share)
        patient = Patient.objects.create(
            full_name=share.name or share.abha_address,
            gender=GENDER_MAP.get((share.gender or "").upper()[:1], "Other"),
            date_of_birth=dob,
            age_years=age_years,
            mobile_no=share.phone_number,
            address=share.address_line,
            district=share.district or None,
            state=share.state or None,
            pincode=share.pincode or None,
            abha_number=share.abha_number or None,
            abha_address=share.abha_address,
            abha_verified=True,
            abha_consent=True,  # the patient chose to share their ABHA profile with us
        )
        return patient, True

    @staticmethod
    def _dob(share):
        try:
            year = int(share.year_of_birth)
        except (TypeError, ValueError):
            return None, None
        try:
            return date(year, int(share.month_of_birth), int(share.day_of_birth)), None
        except (TypeError, ValueError):
            return None, max(timezone.localdate().year - year, 0)

    # ── Gateway replies ─────────────────────────────────

    @staticmethod
    def send_on_share(share, request_id: str):
        payload = {
            "acknowledgement": {
                "status": "SUCCESS",
                "abhaAddress": share.abha_address,
                "profile": {
                    "context": share.context,
                    "tokenNumber": share.token_number,
                    "expiry": str(TOKEN_VALIDITY_SECONDS),
                },
            },
            "response": {"requestId": request_id},
        }
        try:
            abdm.gateway_post(ON_SHARE_PATH, payload, extra_headers={"X-HIP-ID": share.hip_id})
            share.on_share_sent, share.on_share_error = True, ""
        except Exception as e:
            logger.error("[ScanShare] on-share failed: %s", e)
            share.on_share_sent, share.on_share_error = False, str(e)[:255]
        share.save(update_fields=["on_share_sent", "on_share_error"])

    @staticmethod
    def send_on_share_error(request_id: str, hip_id: str, message: str):
        payload = {
            "error": {"code": "1000", "message": message},
            "response": {"requestId": request_id},
        }
        try:
            abdm.gateway_post(ON_SHARE_PATH, payload, extra_headers={"X-HIP-ID": hip_id})
        except Exception as e:
            logger.error("[ScanShare] on-share error reply failed: %s", e)
