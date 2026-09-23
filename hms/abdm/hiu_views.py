"""
ABDM M3 (HIU role) callback views -- the endpoints ABDM's HIE-CM gateway
and other HIPs call while we're acting as a requester of a patient's
records. See hms/abdm/services/hiu.py for the actual logic; these views
are thin: parse the incoming payload, delegate to HIUService, return the
status code the M3 sandbox doc specifies for each callback.
"""

import json
import logging

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from hms.abdm.services.hiu import HIUService

logger = logging.getLogger("hms.abdm.hiu_views")


@csrf_exempt
def abdm_hiu_consent_on_init(request):
    """
    CM's ack for our consent-request/init call (M3 doc §4.3.2). Body:
    {consentRequest: {id}, error, response: {requestId}}
    """
    if request.method != "POST":
        return HttpResponse(status=405)
    try:
        data       = json.loads(request.body)
        request_id = data.get("response", {}).get("requestId")
        error      = data.get("error")
        consent_request_id = data.get("consentRequest", {}).get("id")
        HIUService.record_consent_request_ack(request_id, consent_request_id, error)
    except Exception as e:
        logger.error(f"[M3] consent on-init error: {e}")
    return HttpResponse(status=202)


@csrf_exempt
def abdm_hiu_consent_notify(request):
    """
    CM notifies us of the patient's grant/deny/revoke decision (M3 doc
    §4.3.3). Body: {notification: {consentRequestId, status, reason,
    consentArtefacts: [{id}, ...]}}. We must separately ack this via
    §4.3.4 (the HTTP 202 below is not that ack), then kick off fetching
    each granted artefact.
    """
    if request.method != "POST":
        return HttpResponse(status=405)
    try:
        data          = json.loads(request.body)
        request_id    = request.headers.get("REQUEST-ID", "")
        notification  = data.get("notification", {})
        consent_request_id = notification.get("consentRequestId")
        status        = notification.get("status", "")
        consent_ids   = [c["id"] for c in notification.get("consentArtefacts", []) if c.get("id")]

        HIUService.ack_consent_notify(request_id, consent_ids, status="OK")

        stubs = HIUService.record_consent_decision(consent_request_id, status, consent_ids)
        for stub in stubs:
            HIUService.fetch_artefact(stub.consent_id)
    except Exception as e:
        logger.error(f"[M3] consent notify error: {e}")
    return HttpResponse(status=202)


@csrf_exempt
def abdm_hiu_consent_on_fetch(request):
    """
    CM delivers the full consent artefact (M3 doc §4.3.8). Body:
    {consent: {status, consentDetail: {...}, signature}, error, response: {requestId}}
    """
    if request.method != "POST":
        return HttpResponse(status=405)
    try:
        data    = json.loads(request.body)
        consent = data.get("consent")
        if consent:
            HIUService.store_fetched_artefact(consent)
    except Exception as e:
        logger.error(f"[M3] consent on-fetch error: {e}")
    return HttpResponse(status=200)


@csrf_exempt
def abdm_hiu_health_information_on_request(request):
    """
    CM's ack for our health-information/request call, assigning the
    transactionId the HIP will use when pushing data (M3 doc §5.3.2).
    Body: {hiRequest: {transactionId, sessionStatus}, error, response: {requestId}}
    """
    if request.method != "POST":
        return HttpResponse(status=405)
    try:
        data        = json.loads(request.body)
        request_id  = data.get("response", {}).get("requestId")
        error       = data.get("error")
        transaction_id = data.get("hiRequest", {}).get("transactionId")
        HIUService.record_health_information_ack(request_id, transaction_id, error)
    except Exception as e:
        logger.error(f"[M3] health-information on-request error: {e}")
    return HttpResponse(status=200)


@csrf_exempt
def abdm_hiu_health_information_transfer(request):
    """
    Our own dataPushUrl -- the HIP pushes the actual encrypted health
    records here (same payload shape HIPService.transfer_health_data
    sends, from the opposite side). Decrypts, stores, and reports receipt
    status back to the CM via HIUService.notify_received.
    """
    if request.method != "POST":
        return HttpResponse(status=405)
    try:
        data           = json.loads(request.body)
        transaction_id = data.get("transactionId")
        entries        = data.get("entries", [])
        key_material   = data.get("keyMaterial", {})

        from hms.models import ABDMHealthInformationRequest
        hi_request = ABDMHealthInformationRequest.objects.filter(transaction_id=transaction_id).first()

        status_responses = HIUService.receive_data_push(transaction_id, entries, key_material)
        if hi_request and status_responses:
            HIUService.notify_received(hi_request, status_responses)
    except Exception as e:
        logger.error(f"[M3] health-information transfer error: {e}")
        return JsonResponse({"error": str(e)}, status=500)
    return HttpResponse(status=202)
