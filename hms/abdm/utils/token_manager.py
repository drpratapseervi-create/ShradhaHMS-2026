import requests
import time
from django.conf import settings

TOKEN_CACHE = {
    "token": None,
    "expiry": 0
}


def get_token():
    # ✅ Use cached token if valid
    if TOKEN_CACHE["token"] and TOKEN_CACHE["expiry"] > time.time():
        return TOKEN_CACHE["token"]

    url = f"{settings.ABDM_BASE_URL}/sessions"

    payload = {
        "clientId": settings.ABDM_CLIENT_ID,
        "clientSecret": settings.ABDM_CLIENT_SECRET
    }

    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        data = response.json()

        token = data.get("accessToken")

        if not token:
            raise Exception("ABDM token not received")

        # ✅ Save token
        TOKEN_CACHE["token"] = token
        TOKEN_CACHE["expiry"] = time.time() + 2800  # safer buffer

        return token

    except requests.exceptions.RequestException as e:
        print("ABDM TOKEN ERROR:", str(e))
        return None

    except Exception as e:
        print("ABDM TOKEN FAILURE:", str(e))
        return None