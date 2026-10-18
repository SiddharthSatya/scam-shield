"""Thin client for the Scam Shield API, playing the role of the bank's backend."""

import logging
import subprocess
import threading
import time
from typing import Any

import httpx
from google.auth import exceptions as auth_exceptions
from google.auth.transport.requests import Request
from google.oauth2 import id_token

from ui.config import UISettings

log = logging.getLogger(__name__)

TIMEOUT_S = 30
TOKEN_LIFETIME_S = 45 * 60  # Google ID tokens last 60 min; refresh early


class ApiError(RuntimeError):
    pass


class _IdTokenCache:
    """Google ID token for an IAM-private Cloud Run service.

    On Cloud Run the metadata server issues it. On a laptop with user credentials
    that fails, so we fall back to `gcloud auth print-identity-token`.
    """

    def __init__(self, audience: str) -> None:
        self._audience = audience
        self._token: str | None = None
        self._expires = 0.0
        self._lock = threading.Lock()

    def get(self) -> str:
        with self._lock:
            if self._token is None or time.time() >= self._expires:
                self._token = self._fetch()
                self._expires = time.time() + TOKEN_LIFETIME_S
            return self._token

    def _fetch(self) -> str:
        try:
            return id_token.fetch_id_token(Request(), self._audience)
        except (auth_exceptions.DefaultCredentialsError, auth_exceptions.RefreshError, ValueError):
            log.info("No service-account ID token; falling back to gcloud CLI")
            out = subprocess.run(["gcloud", "auth", "print-identity-token"],
                                 capture_output=True, text=True, check=True, timeout=20)
            return out.stdout.strip()


class ScamShieldClient:
    def __init__(self, settings: UISettings) -> None:
        self._settings = settings
        self._base = settings.scam_shield_url.rstrip("/")
        self._id_tokens = _IdTokenCache(self._base) if settings.use_id_token else None

    def _headers(self) -> dict[str, str]:
        headers = {"X-API-Key": self._settings.api_key.get_secret_value()}
        if self._id_tokens:
            headers["Authorization"] = f"Bearer {self._id_tokens.get()}"
        return headers

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        try:
            r = httpx.post(f"{self._base}{path}", json=payload, headers=self._headers(),
                           timeout=TIMEOUT_S)
        except httpx.HTTPError as e:
            raise ApiError(f"Could not reach Scam Shield: {e}") from e
        if r.status_code >= 400:
            raise ApiError(f"Scam Shield returned {r.status_code}: {r.text[:200]}")
        return r.json() if r.content else None

    def _post_expecting_body(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = self._post(path, payload)
        if result is None:
            raise ApiError(f"Scam Shield returned an empty response for {path}")
        return result

    def check_payment(self, customer_id: str, payee_id: str, amount_inr: float,
                      hour_ist: int) -> dict[str, Any]:
        return self._post_expecting_body("/v1/check-payment", {
            "customer_id": customer_id, "payee_id": payee_id,
            "amount_inr": amount_inr, "hour_ist": hour_ist})

    def submit_context(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post_expecting_body("/v1/context", payload)

    def record_outcome(self, token: str, action: str) -> None:
        self._post("/v1/outcome", {"token": token, "action": action})
