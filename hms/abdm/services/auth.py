import requests
import uuid
from datetime import datetime, timezone, timedelta
from django.conf import settings


class ABDMClient:
    """
    Core ABDM API client — V3 APIs only.
    Token URL  : settings.ABDM_TOKEN_URL  (dev.abdm.gov.in/gateway/v0.5/sessions)
    ABHA URL   : settings.ABDM_BASE_URL   (sandbox.abdm.gov.in/api)
    """

    _access_token = None
    _token_expiry  = None

    @property
    def BASE(self):
        return settings.ABDM_BASE_URL.rstrip("/")

    def get_token(self):
        now = datetime.now(timezone.utc)
        if self._access_token and self._token_expiry and now < self._token_expiry:
            return self._access_token

        resp = requests.post(
            settings.ABDM_TOKEN_URL,
            json={
                "clientId":     settings.ABDM_CLIENT_ID,
                "clientSecret": settings.ABDM_CLIENT_SECRET,
            },
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        token = data.get("accessToken")
        if not token:
            raise ValueError(f"No accessToken in response: {data}")

        self._access_token = token
        self._token_expiry  = now + timedelta(seconds=280)
        return self._access_token

    def _headers(self, extra=None):
        h = {
            "Authorization":  f"Bearer {self.get_token()}",
            "X-CM-ID":        "sbx",
            "Content-Type":   "application/json",
            "Accept":         "application/json",
            "REQUEST-ID":     str(uuid.uuid4()),
            "TIMESTAMP":      datetime.now(timezone.utc).isoformat(),
        }
        if extra:
            h.update(extra)
        return h

    def post(self, path, payload, extra_headers=None):
        r = requests.post(
            f"{self.BASE}{path}",
            json=payload,
            headers=self._headers(extra_headers),
            timeout=20,
        )
        r.raise_for_status()
        return r.json() if r.content else {}

    def get(self, path, params=None, extra_headers=None):
        r = requests.get(
            f"{self.BASE}{path}",
            params=params,
            headers=self._headers(extra_headers),
            timeout=20,
        )
        r.raise_for_status()
        return r.json() if r.content else {}


# Singleton
abdm = ABDMClient()