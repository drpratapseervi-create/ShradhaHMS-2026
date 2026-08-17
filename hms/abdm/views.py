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
from hms.abdm.services.hip import FHIRBuilder, HIPService
from hms.abdm.services.auth import abdm
from hms.models import Patient, Consultation, InvestigationBillItem, InvestigationResult

# ✅ NEW — Our FHIR R4 builder
from hms.fhir_builder import (
    build_op_consultation_bundle,
    build_discharge_summary_bundle,
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
    consultation = get_object_or_404(Consultation, id=consultation_id)
    patient      = consultation.appointment.patient

    if not patient.abha_number:
        messages.warning(request, "No ABHA found for this patient.")
        return redirect("hms:start_consultation", appointment_id=consultation.appointment.id)

    try:
        ref = f"CON-{consultation.id}"

        # ✅ Build FHIR R4 bundle for this consultation
        fhir_bundle = build_op_consultation_bundle(consultation)
        fhir_json   = json.dumps(fhir_bundle)
        logger.info(f"[FHIR] OPD bundle built for consultation {consultation_id} "
                    f"— {len(fhir_bundle['entry'])} entries")

        # HIP-initiated linking with FHIR bundle
        HIPService.add_care_context(
            patient_abha        = patient.abha_address or patient.abha_number,
            care_context_ref    = ref,
            care_context_display= f"OPD – {consultation.appointment.date}",
            fhir_bundle         = fhir_bundle,      # ✅ Pass FHIR bundle
        )

        # Notify ABDM record ready
        HIPService.notify_health_record_ready(
            patient_abha     = patient.abha_number,
            care_context_ref = ref,
            hi_type          = "OPDischargeNote",
            fhir_bundle      = fhir_bundle,          # ✅ Pass FHIR bundle
        )

        # If no ABHA address, send SMS notification
        if not patient.abha_address and patient.mobile_no:
            HIPService.notify_via_sms(
                patient_mobile   = patient.mobile_no,
                hip_id           = None,
                care_context_ref = ref,
            )

        messages.success(request, "✅ Health record pushed to ABDM.")

    except Exception as e:
        logger.error(f"[FHIR] push_care_context error: {e}")
        messages.error(request, f"Push failed: {e}")

    return redirect("hms:start_consultation", appointment_id=consultation.appointment.id)


# ═══════════════════════════════════════════════════════
# M2 — PUSH LAB REPORT
# ═══════════════════════════════════════════════════════

@login_required
def push_lab_report(request, bill_item_id):
    item    = get_object_or_404(InvestigationBillItem, id=bill_item_id)
    patient = item.bill.patient
    results = InvestigationResult.objects.filter(bill_item=item)

    if not patient.abha_number:
        messages.warning(request, "No ABHA found.")
        return redirect("hms:lab_report_print", bill_item_id=bill_item_id)

    try:
        ref = f"LAB-{item.id}"

        # ✅ Build FHIR R4 lab bundle (uses LOINC codes we added in Step 1!)
        fhir_bundle = build_lab_report_bundle(item)
        fhir_json   = json.dumps(fhir_bundle)
        logger.info(f"[FHIR] Lab bundle built for bill_item {bill_item_id} "
                    f"— {len(fhir_bundle['entry'])} entries")

        HIPService.add_care_context(
            patient_abha        = patient.abha_address or patient.abha_number,
            care_context_ref    = ref,
            care_context_display= f"Lab: {item.investigation.name}",
            fhir_bundle         = fhir_bundle,       # ✅ Pass FHIR bundle
        )

        HIPService.notify_health_record_ready(
            patient_abha     = patient.abha_number,
            care_context_ref = ref,
            hi_type          = "DiagnosticReport",
            fhir_bundle      = fhir_bundle,           # ✅ Pass FHIR bundle
        )

        if not patient.abha_address and patient.mobile_no:
            HIPService.notify_via_sms(patient.mobile_no, None, ref)

        messages.success(request, "✅ Lab report pushed to ABDM.")

    except Exception as e:
        logger.error(f"[FHIR] push_lab_report error: {e}")
        messages.error(request, f"Push failed: {e}")

    return redirect("hms:lab_report_print", bill_item_id=bill_item_id)


# ═══════════════════════════════════════════════════════
# M2 CALLBACKS — ABDM GATEWAY CALLS YOUR SERVER
# ═══════════════════════════════════════════════════════

@csrf_exempt
def abdm_on_discover(request):
    """
    ABDM calls this when patient tries to discover their records.
    Your HMS must find the patient and respond with care contexts.
    """
    if request.method != "POST":
        return HttpResponse(status=405)

    try:
        data         = json.loads(request.body)
        request_id   = data.get("requestId")
        txn_id       = data.get("transactionId")
        patient_data = data.get("patient", {})

        patient       = None
        care_contexts = []

        mobile = patient_data.get("unverifiedIdentifiers", [{}])[0].get("value", "")
        abha   = next(
            (i.get("value") for i in patient_data.get("verifiedIdentifiers", [])
             if i.get("type") == "HEALTH_ID"), None
        )

        if abha:
            try:
                patient = Patient.objects.get(abha_number=abha)
            except Patient.DoesNotExist:
                pass

        if not patient and mobile:
            try:
                patient = Patient.objects.get(mobile_no=mobile)
            except Patient.DoesNotExist:
                pass

        if patient:
            # Build care contexts from consultations
            for appt in patient.appointments.filter(
                consultation__isnull=False
            ).select_related("consultation")[:10]:
                care_contexts.append({
                    "ref":     f"CON-{appt.consultation.id}",
                    "display": f"OPD – {appt.date}",
                })

            # Add lab results
            from hms.models import InvestigationBill
            for bill in InvestigationBill.objects.filter(patient=patient, paid=True)[:5]:
                for bill_item in bill.items.all():
                    care_contexts.append({
                        "ref":     f"LAB-{bill_item.id}",
                        "display": f"Lab: {bill_item.investigation.name}",
                    })

            HIPService.respond_to_discovery(request_id, txn_id, patient, care_contexts)

        else:
            abdm.post("/v0.5/care-contexts/on-discover", {
                "requestId":     str(uuid.uuid4()),
                "timestamp":     datetime.now(timezone.utc).isoformat(),
                "transactionId": txn_id,
                "patient":       None,
                "error": {
                    "code":    "CONTEXT_NOT_FOUND",
                    "message": "Patient not found in HIP system."
                },
                "resp": {"requestId": request_id}
            })

        return HttpResponse(status=202)

    except Exception as e:
        logger.error(f"on-discover error: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def abdm_on_init(request):
    """Patient initiated linking — OTP sent, confirm link."""
    if request.method != "POST":
        return HttpResponse(status=405)
    try:
        data       = json.loads(request.body)
        request_id = data.get("requestId")
        txn_id     = data.get("transactionId")

        abdm.post("/v0.5/links/link/on-init", {
            "requestId":     str(uuid.uuid4()),
            "timestamp":     datetime.now(timezone.utc).isoformat(),
            "transactionId": txn_id,
            "link": {
                "referenceNumber":    txn_id,
                "authenticationType": "DIRECT",
                "meta": {
                    "communicationMedium": "MOBILE",
                    "communicationHint":   "OTP sent to registered mobile",
                    "communicationExpiry": datetime.now(timezone.utc).isoformat(),
                }
            },
            "resp": {"requestId": request_id}
        })
        return HttpResponse(status=202)
    except Exception as e:
        logger.error(f"on-init error: {e}")
        return HttpResponse(status=202)


@csrf_exempt
def abdm_on_confirm(request):
    """Patient confirmed linking with OTP — finalize care context link."""
    if request.method != "POST":
        return HttpResponse(status=405)
    try:
        data = json.loads(request.body)
        logger.info(f"[M2] on-confirm: {data}")
        return HttpResponse(status=202)
    except Exception as e:
        logger.error(f"on-confirm error: {e}")
        return HttpResponse(status=202)


@csrf_exempt
def abdm_consent_notify(request):
    """
    ABDM sends consent artifact when patient grants consent.
    Store it so we can verify before sharing health data.
    """
    if request.method != "POST":
        return HttpResponse(status=405)
    try:
        data    = json.loads(request.body)
        consent = data.get("notification", {})
        c_id    = consent.get("consentId") or consent.get("id")
        if c_id:
            HIPService.store_consent(c_id, consent)
            logger.info(f"[M2] Consent stored: {c_id}")
        return HttpResponse(status=202)
    except Exception as e:
        logger.error(f"consent-notify error: {e}")
        return HttpResponse(status=202)


@csrf_exempt
def abdm_data_request(request):
    """
    HIU requests health data after patient gives consent.
    Verify consent → build FHIR R4 bundle → transfer to HIU.
    """
    if request.method != "POST":
        return HttpResponse(status=405)

    try:
        data          = json.loads(request.body)
        txn_id        = data.get("transactionId")
        consent_id    = data.get("hiRequest", {}).get("consent", {}).get("id")
        date_range    = data.get("hiRequest", {}).get("dateRange", {})
        data_push_url = data.get("hiRequest", {}).get("dataPushUrl")
        key_material  = data.get("hiRequest", {}).get("keyMaterial", {})
        hi_types      = data.get("hiRequest", {}).get("hiType", [])

        # Verify consent
        for hi_type in (hi_types if isinstance(hi_types, list) else [hi_types]):
            if not HIPService.verify_consent(consent_id, hi_type):
                logger.warning(f"[M2] Consent {consent_id} not valid for {hi_type}")
                return HttpResponse(status=403)

        # ✅ Build FHIR bundles for records in date range
        fhir_bundles = []

        date_from = date_range.get("from", "")
        date_to   = date_range.get("to", "")

        # Get consultations in date range
        consultations = Consultation.objects.filter(
            appointment__date__gte = date_from[:10] if date_from else "2000-01-01",
            appointment__date__lte = date_to[:10]   if date_to   else "2099-12-31",
        ).select_related("appointment__patient")

        for consultation in consultations:
            try:
                bundle = build_op_consultation_bundle(consultation)
                fhir_bundles.append(bundle)
            except Exception as e:
                logger.warning(f"[FHIR] Could not build bundle for consultation "
                               f"{consultation.id}: {e}")

        # Get lab reports in date range
        lab_items = InvestigationBillItem.objects.filter(
            bill__created_at__date__gte = date_from[:10] if date_from else "2000-01-01",
            bill__created_at__date__lte = date_to[:10]   if date_to   else "2099-12-31",
        ).select_related("bill__patient", "investigation")

        for item in lab_items:
            try:
                bundle = build_lab_report_bundle(item)
                fhir_bundles.append(bundle)
            except Exception as e:
                logger.warning(f"[FHIR] Could not build bundle for lab item "
                               f"{item.id}: {e}")

        logger.info(f"[M2] Data request txn={txn_id}, consent={consent_id}, "
                    f"bundles_built={len(fhir_bundles)}")

        # TODO: Encrypt bundles with key_material and POST to data_push_url
        # HIPService.transfer_health_data(data_push_url, key_material, fhir_bundles)

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