from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from ._shared import logger


@csrf_exempt
def whatsapp_webhook(request):
    logger.info("WhatsApp webhook hit")
    return JsonResponse({"status": "ok"})

