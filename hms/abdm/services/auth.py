import requests
import uuid
from datetime import datetime, timezone, timedelta
from django.conf import settings


class ABDMClient:
    """
    Core ABDM API client — V3 APIs only.
    Token URL  : settings.ABDM_TOKEN_URL  (dev.abdm.gov.in/api/hiecm/gateway/v3/sessions)
    ABHA URL   : settings.ABDM_BASE_URL   (abhasbx.abdm.gov.in/abha/api)
    Gateway URL: settings.ABDM_GATEWAY_URL (dev.abdm.gov.in — M2 HIP linking/consent/data-flow APIs)
    """

    _access_token = None
    _token_expiry  = None

    @property
    def BASE(self):
        return settings.ABDM_BASE_URL.rstrip("/")

    @property
    def GATEWAY_BASE(self):
        return settings.ABDM_GATEWAY_URL.rstrip("/")

    def get_token(self):
        now = datetime.now(timezone.utc)
        if self._access_token and self._token_expiry and now < self._token_expiry:
            return self._access_token

        resp = requests.post(
            settings.ABDM_TOKEN_URL,
            json={
                "clientId":     settings.ABDM_CLIENT_ID,
                "clientSecret": settings.ABDM_CLIENT_SECRET,
                "grantType":    "client_credentials",
            },
            headers={
                "Content-Type": "application/json",
                "REQUEST-ID":   str(uuid.uuid4()),
                "TIMESTAMP":    now.isoformat(),
                "X-CM-ID":      "sbx",
            },
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

    # ── HIE-CM Gateway (M2 linking/consent/data-flow — different host
    #    than the ABHA enrollment BASE above) ────────────────────────

    def gateway_post(self, path, payload, extra_headers=None):
        r = requests.post(
            f"{self.GATEWAY_BASE}{path}",
            json=payload,
            headers=self._headers(extra_headers),
            timeout=20,
        )
        r.raise_for_status()
        return r.json() if r.content else {}

    def gateway_get(self, path, params=None, extra_headers=None):
        r = requests.get(
            f"{self.GATEWAY_BASE}{path}",
            params=params,
            headers=self._headers(extra_headers),
            timeout=20,
        )
        r.raise_for_status()
        return r.json() if r.content else {}


# Singleton
abdm = ABDMClient()