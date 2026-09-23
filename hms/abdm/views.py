"""
ABDM M1 + M2 Views
===================
M1: ABHA creation, verification, linking
M2: Care context linking, consent management, health data transfer
"""

import uuid
import json
import logging
from datetime import datetime, timezone

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse
from django.contrib import messages

from hms.abdm.services.abha import ABHAService
from hms.abdm.services.hip import HIPService
from hms.models import (
    Patient, Consultation, InvestigationBillItem,
    ABDMLinkToken, ABDMCareContext,
)

from hms.fhir_builder import (
    build_op_consultation_bundle,
    build_lab_report_bundle,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════
# M1 FLOW 1 — CREATE ABHA VIA AADHAAR OTP
# ═══════════════════════════════════════════════════════

@login_required
def abha_aadhaar_otp(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)

    if request.method == "POST":
        aadhaar = request.POST.get("aadhaar_number", "").strip()
        if len(aadhaar) != 12 or not aadhaar.isdigit():
            messages.error(request, "Please enter a valid 12-digit Aadhaar number.")
            return render(request, "abdm/abha_aadhaar_form.html", {"patient": patient})
        try:
            result = ABHAService.aadhaar_generate_otp(aadhaar)
            request.session["abha_txn_id"]     = result.get("txnId")
            request.session["abha_patient_id"] = patient_id
            messages.success(request, "OTP sent to Aadhaar-registered mobile.")
            return redirect("hms:abha_verify_otp", patient_id=patient_id)
        except Exception as e:
            messages.error(request, f"ABDM Error: {e}")

    return render(request, "abdm/abha_aadhaar_form.html", {"patient": patient})


@login_required
def abha_verify_otp(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    txn_id  = request.session.get("abha_txn_id")

    if not txn_id:
        messages.error(request, "Session expired. Please start again.")
        return redirect("hms:abha_aadhaar_otp", patient_id=patient_id)

    if request.method == "POST":
        otp = request.POST.get("otp", "").strip()
        try:
            result      = ABHAService.aadhaar_verify_otp(txn_id, otp)
            x_token     = result.get("tokens", {}).get("token") or result.get("token")
            abha_number = result.get("ABHANumber") or result.get("healthIdNumber")
            abha_addr   = result.get("preferredAbhaAddress") or result.get("healthId")

            if abha_number:
                patient.abha_number   = abha_number
                patient.abha_address  = abha_addr
                patient.abha_verified = True
                patient.save()

            if x_token:
                request.session["abha_x_token"] = x_token

            request.session.pop("abha_txn_id", None)
            messages.success(request, f"✅ ABHA created: {abha_number}")

            if not abha_addr and x_token:
                try:
                    sugg = ABHAService.suggest_abha_address(x_token)
                    request.session["abha_suggestions"] = sugg.get("abhaAddressList", [])
                except Exception:
                    pass
                return redirect("hms:abha_create_address", patient_id=patient_id)

            return redirect("hms:patient_update", pk=patient_id)

        except Exception as e:
            messages.error(request, f"OTP verification failed: {e}")

    return render(request, "abdm/abha_otp_form.html", {"patient": patient})


# ═══════════════════════════════════════════════════════
# M1 FLOW 2 — CREATE ABHA ADDRESS
# ═══════════════════════════════════════════════════════

@login_required
def abha_create_address(request, patient_id):
    patient     = get_object_or_404(Patient, id=patient_id)
    x_token     = request.session.get("abha_x_token")
    suggestions = request.session.get("abha_suggestions", [])

    if not x_token:
        messages.error(request, "Session expired.")
        return redirect("hms:patient_update", pk=patient_id)

    if request.method == "POST":
        abha_address = request.POST.get("abha_address", "").strip()
        txn_id       = request.session.get("abha_txn_id", "")
        try:
            ABHAService.create_abha_address(txn_id, abha_address, x_token)
            patient.abha_address = f"{abha_address}@abdm"
            patient.save()
            request.session.pop("abha_x_token", None)
            messages.success(request, f"✅ ABHA Address: {patient.abha_address}")
            return redirect("hms:patient_update", pk=patient_id)
        except Exception as e:
            messages.error(request, f"Error: {e}")

    return render(request, "abdm/abha_address_form.html", {
        "patient": patient, "suggestions": suggestions
    })


# ═══════════════════════════════════════════════════════
# M1 FLOW 3 — DOWNLOAD ABHA CARD
# ═══════════════════════════════════════════════════════

@login_required
def abha_download_card(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    x_token = request.session.get("abha_x_token")
    fmt     = request.GET.get("format", "png")

    if not x_token:
        messages.info(request, "Please verify ABHA to download card.")
        return redirect("hms:abha_verify_returning", patient_id=patient_id)

    try:
        if fmt == "pdf":
            data         = ABHAService.download_abha_card_pdf(x_token)
            content_type = "application/pdf"
            filename     = f"ABHA_{patient.abha_number}.pdf"
        else:
            data         = ABHAService.download_abha_card_png(x_token)
            content_type = "image/png"
            filename     = f"ABHA_{patient.abha_number}.png"

        resp = HttpResponse(data, content_type=content_type)
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp
    except Exception as e:
        messages.error(request, f"Card download failed: {e}")
        return redirect("hms:patient_update", pk=patient_id)


# ═══════════════════════════════════════════════════════
# M1 FLOW 4 — VERIFY RETURNING PATIENT
# ═══════════════════════════════════════════════════════

@login_required
def abha_verify_returning(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    step    = request.session.get("abha_verify_step", "enter_id")

    if request.method == "POST":
        if step == "enter_id":
            verify_id   = request.POST.get("verify_id", "").strip()
            verify_type = request.POST.get("verify_type", "abha-number")
            try:
                if verify_type == "abha-number":
                    exists = ABHAService.check_abha_exists(verify_id)
                    if not exists.get("exists"):
                        messages.error(request, "ABHA number not found.")
                        return render(request, "abdm/abha_verify_returning.html",
                                      {"patient": patient, "step": step})
                    result = ABHAService.verify_send_otp(verify_id)
                elif verify_type == "mobile":
                    result = ABHAService.verify_by_mobile(verify_id)
                elif verify_type == "aadhaar":
                    result = ABHAService.verify_by_aadhaar(verify_id)
                else:
                    result = ABHAService.search_by_health_id(verify_id)

                request.session["abha_verify_txn"]  = result.get("txnId")
                request.session["abha_verify_step"] = "verify_otp"
                messages.success(request, "OTP sent.")
            except Exception as e:
                messages.error(request, f"Error: {e}")

        elif step == "verify_otp":
            otp    = request.POST.get("otp", "").strip()
            txn_id = request.session.get("abha_verify_txn")
            try:
                result  = ABHAService.verify_by_otp(txn_id, otp)
                x_token = result.get("tokens", {}).get("token") or result.get("token")

                if x_token:
                    profile = ABHAService.get_profile(x_token)
                    patient.abha_number   = profile.get("ABHANumber") or patient.abha_number
                    patient.abha_address  = profile.get("preferredAbhaAddress") or patient.abha_address
                    patient.abha_verified = True
                    patient.save()
                    request.session["abha_x_token"] = x_token

                request.session.pop("abha_verify_step", None)
                request.session.pop("abha_verify_txn", None)
                messages.success(request, "✅ ABHA verified.")
                return redirect("hms:patient_update", pk=patient_id)
            except Exception as e:
                messages.error(request, f"OTP failed: {e}")

    return render(request, "abdm/abha_verify_returning.html",
                  {"patient": patient, "step": step})


# ═══════════════════════════════════════════════════════
# M1 FLOW 5 — LINK EXISTING ABHA
# ═══════════════════════════════════════════════════════

@login_required
def abha_link_existing(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    step    = request.session.get("abha_link_step", "enter_abha")

    if request.method == "POST":
        if step == "enter_abha":
            abha_id = request.POST.get("abha_number", "").strip()
            try:
                exists = ABHAService.check_abha_exists(abha_id)
                if not exists.get("exists"):
                    messages.error(request, "ABHA not found.")
                else:
                    result = ABHAService.verify_send_otp(abha_id)
                    request.session["abha_txn_id"]    = result.get("txnId")
                    request.session["abha_link_step"] = "verify_otp"
                    request.session["abha_number"]    = abha_id
                    messages.success(request, "OTP sent.")
            except Exception as e:
                messages.error(request, f"Error: {e}")

        elif step == "verify_otp":
            otp    = request.POST.get("otp", "").strip()
            txn_id = request.session.get("abha_txn_id")
            try:
                result  = ABHAService.verify_by_otp(txn_id, otp)
                x_token = result.get("tokens", {}).get("token") or result.get("token")
                if x_token:
                    profile = ABHAService.get_profile(x_token)
                    patient.abha_number   = profile.get("ABHANumber") or request.session.get("abha_number")
                    patient.abha_address  = profile.get("preferredAbhaAddress", "")
                    patient.abha_verified = True
                    patient.save()

                request.session.pop("abha_link_step", None)
                request.session.pop("abha_txn_id", None)
                messages.success(request, f"✅ ABHA linked: {patient.abha_number}")
                return redirect("hms:patient_update", pk=patient_id)
            except Exception as e:
                messages.error(request, f"OTP failed: {e}")

    return render(request, "abdm/abha_link.html", {"patient": patient, "step": step})


# ═══════════════════════════════════════════════════════
# M1 FLOW 6 — DRIVING LICENSE
# ═══════════════════════════════════════════════════════

@login_required
def abha_driving_license(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    step    = request.session.get("abha_dl_step", "enter_mobile")

    if request.method == "POST":
        if step == "enter_mobile":
            mobile = request.POST.get("mobile", "").strip()
            try:
                result = ABHAService.dl_generate_otp(mobile)
                request.session["abha_txn_id"]  = result.get("txnId")
                request.session["abha_dl_step"] = "verify_otp"
                messages.success(request, "OTP sent.")
            except Exception as e:
                messages.error(request, f"Error: {e}")

        elif step == "verify_otp":
            otp    = request.POST.get("otp", "").strip()
            txn_id = request.session.get("abha_txn_id")
            try:
                ABHAService.dl_verify_otp(txn_id, otp)
                request.session["abha_dl_step"] = "enter_dl"
                messages.success(request, "OTP verified. Enter DL details.")
            except Exception as e:
                messages.error(request, f"OTP failed: {e}")

        elif step == "enter_dl":
            txn_id = request.session.get("abha_txn_id")
            try:
                result = ABHAService.dl_enroll(
                    txn_id,
                    dl_number  = request.POST.get("dl_number", "").strip(),
                    dob        = request.POST.get("dob", "").strip(),
                    first_name = request.POST.get("first_name", "").strip(),
                    last_name  = request.POST.get("last_name", "").strip(),
                    gender     = request.POST.get("gender", "M").strip(),
                )
                x_token     = result.get("tokens", {}).get("token")
                abha_number = result.get("ABHANumber")
                patient.abha_number   = abha_number
                patient.abha_verified = True
                patient.save()
                if x_token:
                    request.session["abha_x_token"] = x_token
                request.session.pop("abha_dl_step", None)
                messages.success(request, f"✅ ABHA via DL: {abha_number}")
                return redirect("hms:patient_update", pk=patient_id)
            except Exception as e:
                messages.error(request, f"DL enrollment failed: {e}")

    return render(request, "abdm/abha_driving_license.html",
                  {"patient": patient, "step": step})


# ═══════════════════════════════════════════════════════
# M2 — PUSH CARE CONTEXT (OPD Consultation)
# ═══════════════════════════════════════════════════════

@login_required
def push_care_context(request, consultation_id):
    """Manual retry button for the automatic ABDM push already attempted
    on consultation completion (see hms/views/opd.py start_consultation)."""
    consultation = get_object_or_404(Consultation, id=consultation_id)
    patient      = consultation.appointment.patient

    if not (patient.abha_address and patient.abha_verified):
        if patient.mobile_no:
            HIPService.notify_via_sms(patient.mobile_no)
        messages.warning(request, "No verified ABHA address for this patient — sent SMS notification instead." if patient.mobile_no else "No verified ABHA address for this patient.")
        return redirect("hms:start_consultation", appointment_id=consultation.appointment.id)

    try:
        HIPService.notify_opd_consultation(consultation)
        messages.success(request, "✅ Health record pushed to ABDM.")
    except Exception as e:
        logger.error(f"[M2] push_care_context error: {e}")
        messages.error(request, f"Push failed: {e}")

    return redirect("hms:start_consultation", appointment_id=consultation.appointment.id)


# ═══════════════════════════════════════════════════════
# M2 — PUSH LAB REPORT
# ═══════════════════════════════════════════════════════

@login_required
def push_lab_report(request, bill_item_id):
    """Manual retry button for the automatic ABDM push already attempted
    on result entry (see hms/views/lab.py lab_result_entry)."""
    item    = get_object_or_404(InvestigationBillItem, id=bill_item_id)
    patient = item.bill.patient

    if not (patient.abha_address and patient.abha_verified):
        if patient.mobile_no:
            HIPService.notify_via_sms(patient.mobile_no)
        messages.warning(request, "No verified ABHA address for this patient — sent SMS notification instead." if patient.mobile_no else "No verified ABHA address for this patient.")
        return redirect("hms:lab_report_print", bill_item_id=bill_item_id)

    try:
        HIPService.notify_lab_report(item)
        messages.success(request, "✅ Lab report pushed to ABDM.")
    except Exception as e:
        logger.error(f"[M2] push_lab_report error: {e}")
        messages.error(request, f"Push failed: {e}")

    return redirect("hms:lab_report_print", bill_item_id=bill_item_id)


# ═══════════════════════════════════════════════════════
# M2 CALLBACKS — ABDM GATEWAY CALLS YOUR SERVER
# ═══════════════════════════════════════════════════════

@csrf_exempt
def abdm_on_discover(request):
    """
    ABDM calls this when a patient tries to discover their records from a
    PHR app (M2 doc §5.3.2). Real incoming shape:
    {transactionId, patient: {id, verifiedIdentifiers: [{type, value}],
                               unverifiedIdentifiers: [...], name, gender,
                               yearOfBirth}}
    verifiedIdentifiers type is "ABHA_NUMBER" / "MOBILE"; unverifiedIdentifiers
    commonly carries "MR" (our own hospital ID).
    """
    if request.method != "POST":
        return HttpResponse(status=405)

    try:
        data         = json.loads(request.body)
        request_id   = request.headers.get("REQUEST-ID", "")
        txn_id       = data.get("transactionId")
        patient_data = data.get("patient", {})

        verified   = patient_data.get("verifiedIdentifiers", [])
        unverified = patient_data.get("unverifiedIdentifiers", [])

        abha_number = next((i.get("value") for i in verified if i.get("type") == "ABHA_NUMBER"), None)
        mobile      = next((i.get("value") for i in verified if i.get("type") == "MOBILE"), None)
        mr_number   = next((i.get("value") for i in unverified if i.get("type") == "MR"), None)

        patient    = None
        matched_by = []

        if abha_number:
            patient = HIPService.find_patient_by_abha(abha_number=abha_number)
            if patient:
                matched_by = ["ABHA_NUMBER"]
        if not patient and mobile:
            patient = Patient.objects.filter(mobile_no=mobile).first()
            if patient:
                matched_by = ["MOBILE"]
        if not patient and mr_number:
            patient = Patient.objects.filter(uhid=mr_number).first()
            if patient:
                matched_by = ["MR"]

        if patient:
            HIPService.respond_to_discovery(request_id, txn_id, patient, matched_by)
        else:
            HIPService.gateway_post_on_discover_not_found(request_id, txn_id)

        return HttpResponse(status=202)

    except Exception as e:
        logger.error(f"on-discover error: {e}")
        return HttpResponse(status=202)


@csrf_exempt
def abdm_on_init(request):
    """
    ABDM calls this to initiate user-initiated linking after a successful
    discovery (M2 doc §5.3.6). Real incoming shape:
    {transactionId, abhaAddress, patient: [{referenceNumber, careContexts, hiType, count}]}
    We match the patient by abhaAddress (already stored on Patient once M1
    ABHA verification has run) and respond with our own link reference + OTP.
    """
    if request.method != "POST":
        return HttpResponse(status=405)
    try:
        data         = json.loads(request.body)
        request_id   = request.headers.get("REQUEST-ID", "")
        txn_id       = data.get("transactionId")
        abha_address = data.get("abhaAddress")

        patient = HIPService.find_patient_by_abha(abha_address=abha_address) if abha_address else None
        if patient:
            HIPService.respond_to_link_init(request_id, txn_id, patient)
        else:
            logger.warning(f"[M2] on-init: no patient found for abhaAddress={abha_address}")
        return HttpResponse(status=202)
    except Exception as e:
        logger.error(f"on-init error: {e}")
        return HttpResponse(status=202)


@csrf_exempt
def abdm_on_confirm(request):
    """
    ABDM relays the patient-entered OTP here to finalize user-initiated
    linking (M2 doc §5.3.10). Real incoming shape:
    {confirmation: {token, linkRefNumber}}
    """
    if request.method != "POST":
        return HttpResponse(status=405)
    try:
        data          = json.loads(request.body)
        request_id    = request.headers.get("REQUEST-ID", "")
        confirmation  = data.get("confirmation", {})
        token         = confirmation.get("token")
        link_ref      = confirmation.get("linkRefNumber")

        from hms.models import ABDMLinkingSession, ABDMCareContext
        session = ABDMLinkingSession.objects.filter(link_reference=link_ref).first()

        if session and not session.confirmed_at and session.otp == token:
            session.confirmed_at = datetime.now(timezone.utc)
            session.save(update_fields=["confirmed_at"])
            ABDMCareContext.objects.filter(patient=session.patient).update(
                linked=True, linked_at=datetime.now(timezone.utc)
            )
            HIPService.respond_to_link_confirm(request_id, session)
        else:
            logger.warning(f"[M2] on-confirm: OTP mismatch or unknown "
                            f"linkRefNumber={link_ref}")
        return HttpResponse(status=202)
    except Exception as e:
        logger.error(f"on-confirm error: {e}")
        return HttpResponse(status=202)


@csrf_exempt
def abdm_hip_on_generate_token(request):
    """
    ABDM Gateway delivers the actual link token here (M2 §4.3.2) —
    generate_link_token()'s own HTTP response never carries it. Once
    received, immediately proceed to step 2 (link_care_context) for
    whatever ABDMCareContext rows are still unlinked for this patient.
    Body: {abhaAddress, linkToken, response: {requestId}}
    """
    if request.method != "POST":
        return HttpResponse(status=405)
    try:
        data       = json.loads(request.body)
        request_id = data.get("response", {}).get("requestId")
        link_token = data.get("linkToken")
        abha_addr  = data.get("abhaAddress")

        pending = ABDMLinkToken.objects.filter(request_id=request_id).first()
        if pending and link_token:
            pending.token        = link_token
            pending.abha_address = abha_addr or pending.abha_address
            pending.received_at  = datetime.now(timezone.utc)
            pending.save(update_fields=["token", "abha_address", "received_at"])

            unlinked = ABDMCareContext.objects.filter(
                patient=pending.patient, linked=False
            )
            HIPService.link_care_context(pending.patient, link_token, unlinked)
        else:
            logger.warning(f"[M2] on-generate-token: no pending ABDMLinkToken "
                            f"for requestId={request_id}")
    except Exception as e:
        logger.error(f"on-generate-token error: {e}")
    return HttpResponse(status=202)


@csrf_exempt
def abdm_on_link_carecontext(request):
    """
    ABDM Gateway's ack for link_care_context() (M2 §4.3.4) — confirms or
    rejects the care contexts submitted in that call, matched by
    response.requestId (stamped as pending_request_id when submitted).
    Body: {abhaAddress, status, response: {requestId}}
    Body (error): {error: {code, message}, response: {requestId}}
    """
    if request.method != "POST":
        return HttpResponse(status=405)
    try:
        data       = json.loads(request.body)
        request_id = data.get("response", {}).get("requestId")
        error      = data.get("error")
        status_msg = data.get("status", "")

        matched = ABDMCareContext.objects.filter(pending_request_id=request_id)
        if error:
            logger.warning(f"[M2] on_carecontext error for requestId={request_id}: {error}")
            matched.update(pending_request_id="")
        elif "success" in status_msg.lower():
            matched.update(linked=True, linked_at=datetime.now(timezone.utc),
                           pending_request_id="")
        else:
            logger.warning(f"[M2] on_carecontext unexpected status for "
                            f"requestId={request_id}: {status_msg}")
            matched.update(pending_request_id="")
    except Exception as e:
        logger.error(f"on_carecontext error: {e}")
    return HttpResponse(status=202)


@csrf_exempt
def abdm_on_notify(request):
    """
    ABDM Gateway's acknowledgement of a care-context notify call
    (HIPService.notify_care_context_update). The notify call itself
    only gets a 202 Accepted; the actual acknowledgement/result of
    processing that notification arrives here.
    Body: {requestId, timestamp, acknowledgement: {status}, response: {requestId}}
    """
    if request.method != "POST":
        return HttpResponse(status=405)
    try:
        data = json.loads(request.body)
        logger.info(
            f"[M2] on-notify ack: requestId={data.get('requestId')} "
            f"status={data.get('acknowledgement', {}).get('status')} "
            f"respRequestId={data.get('response', {}).get('requestId')}"
        )
    except Exception as e:
        logger.error(f"on-notify error: {e}")
    return HttpResponse(status=202)


@csrf_exempt
def abdm_consent_notify(request):
    """
    ABDM sends the consent artifact here when a patient grants/revokes
    consent (M2 doc §6.3.1). Real incoming shape is flat (no "notification"
    wrapper): {status, consentId, patient, hip, purpose, hiTypes,
    permission: {...}, signature, ...}. Store it, then ack separately
    (§6.3.2) -- the HTTP 202 below is not the same as that ack.
    """
    if request.method != "POST":
        return HttpResponse(status=405)
    try:
        data       = json.loads(request.body)
        request_id = request.headers.get("REQUEST-ID", "")
        c_id       = data.get("consentId")
        if c_id:
            HIPService.store_consent(c_id, data)
            HIPService.ack_consent_notify(request_id, c_id, status="OK")
            logger.info(f"[M2] Consent stored + acked: {c_id}")
        return HttpResponse(status=202)
    except Exception as e:
        logger.error(f"consent-notify error: {e}")
        return HttpResponse(status=202)


@csrf_exempt
def abdm_data_request(request):
    """
    HIU requests health data after patient gave consent (M2 doc §6.3.3).
    Real incoming shape: {hiRequest: {consent: {id}, dateRange: {from, to},
    dataPushUrl, keyMaterial}} -- no hiTypes/transactionId here; hiTypes
    were fixed when the consent was granted (stored on ABDMConsent), and
    we mint our own transactionId to track this request end to end.

    Flow: ack immediately (§6.3.4, separate from the HTTP 202 below) ->
    look up the SPECIFIC consented patient (by the consent's ABHA address --
    the previous version of this view built bundles from EVERY patient's
    records in the date range, regardless of whose consent this was) ->
    build FHIR bundles only for that patient, only for consented hiTypes ->
    push (§6.3.5) -> report transfer status (§6.3.6).
    """
    if request.method != "POST":
        return HttpResponse(status=405)

    try:
        data          = json.loads(request.body)
        request_id    = request.headers.get("REQUEST-ID", "")
        hi_request    = data.get("hiRequest", {})
        consent_id    = hi_request.get("consent", {}).get("id")
        date_range    = hi_request.get("dateRange", {})
        data_push_url = hi_request.get("dataPushUrl")

        transaction_id = str(uuid.uuid4())
        HIPService.ack_health_info_request(request_id, transaction_id)

        from hms.models import ABDMConsent
        consent = ABDMConsent.objects.filter(consent_id=consent_id).first()
        if not consent or consent.status != "GRANTED":
            logger.warning(f"[M2] data-request: consent {consent_id} not GRANTED")
            return HttpResponse(status=202)

        patient = HIPService.find_patient_by_abha(abha_address=consent.patient_abha)
        if not patient:
            logger.warning(f"[M2] data-request: no patient for consent {consent_id} "
                            f"(abha={consent.patient_abha})")
            return HttpResponse(status=202)

        consented_types = {t.upper() for t in json.loads(consent.hi_types or "[]")}

        date_from = date_range.get("from", "")[:10] or "2000-01-01"
        date_to   = date_range.get("to", "")[:10] or "2099-12-31"

        entries = []

        if not consented_types or "OPCONSULTATION" in consented_types:
            consultations = Consultation.objects.filter(
                appointment__patient  = patient,
                appointment__date__gte = date_from,
                appointment__date__lte = date_to,
            ).select_related("appointment__patient")
            for consultation in consultations:
                try:
                    bundle = build_op_consultation_bundle(consultation)
                    entries.append(HIPService.package_health_data(
                        bundle, f"CON-{consultation.id}"
                    ))
                except Exception as e:
                    logger.warning(f"[FHIR] Could not build bundle for consultation "
                                   f"{consultation.id}: {e}")

        if not consented_types or "DIAGNOSTICREPORT" in consented_types:
            lab_items = InvestigationBillItem.objects.filter(
                bill__patient = patient,
                bill__created_at__date__gte = date_from,
                bill__created_at__date__lte = date_to,
            ).select_related("bill__patient", "investigation")
            for item in lab_items:
                try:
                    bundle = build_lab_report_bundle(item)
                    entries.append(HIPService.package_health_data(
                        bundle, f"LAB-{item.id}"
                    ))
                except Exception as e:
                    logger.warning(f"[FHIR] Could not build bundle for lab item "
                                   f"{item.id}: {e}")

        logger.info(f"[M2] Data request txn={transaction_id}, consent={consent_id}, "
                    f"patient={patient.id}, entries_built={len(entries)}")

        if entries and data_push_url:
            result = HIPService.transfer_health_data(transaction_id, data_push_url, entries)
            transferred = result.get("status") == "transferred"
            HIPService.notify_transfer_status(
                consent_id, transaction_id,
                session_status = "TRANSFERRED" if transferred else "FAILED",
                status_responses = [
                    {
                        "careContextReference": e["careContextReference"],
                        "hiStatus":            "DELIVERED" if transferred else "ERRORED",
                    }
                    for e in entries
                ],
            )

        return HttpResponse(status=202)

    except Exception as e:
        logger.error(f"data-request error: {e}")
        return HttpResponse(status=202)


# ═══════════════════════════════════════════════════════
# UHI STUBS
# ═══════════════════════════════════════════════════════

@csrf_exempt
def uhi_search(request):
    return JsonResponse({"status": "ok"})


@csrf_exempt
def uhi_confirm(request):
    return JsonResponse({"status": "confirmed"})