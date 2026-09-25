"""
ABDM M1 Scan & Share: the HIE-CM callback (patient shared their ABHA profile
by scanning our counter QR) and the reception queue that shows those patients
with their token numbers. Logic lives in hms/abdm/services/scan_share.py.
"""

import json
import logging
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from hms.abdm.services.scan_share import ScanShareService
from hms.decorators import role_required
from hms.models import ABDMScanShare

logger = logging.getLogger(__name__)


@csrf_exempt
def abdm_patient_share(request):
    """HIE-CM: POST /api/v3/hip/patient/share (always acknowledged with 202)."""
    if request.method != "POST":
        return HttpResponse(status=405)
    try:
        data = json.loads(request.body)
        ScanShareService.handle_share(
            request_id=request.headers.get("REQUEST-ID", ""),
            hip_id=request.headers.get("X-HIP-ID", ""),
            data=data,
        )
    except Exception as e:
        logger.error(f"patient/share error: {e}")
    return HttpResponse(status=202)


@login_required
@role_required("reception", "doctor", "admin")
def scan_share_queue(request):
    day = timezone.localdate()
    if request.GET.get("date"):
        try:
            day = datetime.strptime(request.GET["date"], "%Y-%m-%d").date()
        except ValueError:
            pass
    shares = (
        ABDMScanShare.objects.filter(token_date=day)
        .select_related("patient")
        .order_by("status", "created_at")  # WAITING before DONE, then arrival order
    )
    return render(request, "abdm/scan_share_queue.html", {
        "shares": shares,
        "day": day,
        "is_today": day == timezone.localdate(),
        "waiting_count": sum(1 for s in shares if s.status == "WAITING"),
    })


@login_required
@role_required("reception", "doctor", "admin")
@require_POST
def scan_share_mark(request, share_id):
    share = get_object_or_404(ABDMScanShare, id=share_id)
    share.status = "DONE" if share.status == "WAITING" else "WAITING"
    share.save(update_fields=["status"])
    return redirect(f"{reverse('hms:scan_share_queue')}?date={share.token_date:%Y-%m-%d}")
