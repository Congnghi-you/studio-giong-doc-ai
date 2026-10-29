import hashlib
import hmac
import json
import os
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ANNUAL_PRICE_USD = 49.90
ACCESS_DAYS = 365
STT_MINUTES_PER_WINDOW = 300
STT_WINDOW_DAYS = 30
STT_MAX_JOB_SECONDS = 60 * 60


class BillingError(Exception):
    pass


class AuthenticationRequired(BillingError):
    pass


class ProviderResponseError(BillingError):
    def __init__(self, status_code):
        super().__init__(f"Billing provider returned HTTP {status_code}.")
        self.status_code = status_code


class BillingConfig:
    def __init__(self):
        self.enabled = os.getenv("BILLING_ENABLED", "").lower() in ("1", "true", "yes")
        self.supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.supabase_anon_key = os.getenv("SUPABASE_ANON_KEY", "")
        self.supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        self.paddle_api_key = os.getenv("PADDLE_API_KEY", "")
        self.paddle_client_token = os.getenv("PADDLE_CLIENT_TOKEN", "")
        self.paddle_webhook_secret = os.getenv("PADDLE_WEBHOOK_SECRET", "")
        self.paddle_price_id = os.getenv("PADDLE_PRICE_ID", "")
        self.paddle_environment = os.getenv("PADDLE_ENVIRONMENT", "sandbox").lower()

    @property
    def configured(self):
        required = (
            self.supabase_url,
            self.supabase_anon_key,
            self.supabase_service_role_key,
            self.paddle_api_key,
            self.paddle_client_token,
            self.paddle_webhook_secret,
            self.paddle_price_id,
        )
        return all(required) and self.paddle_environment in ("sandbox", "production")

    @property
    def paddle_api_url(self):
        if self.paddle_environment == "production":
            return "https://api.paddle.com"
        return "https://sandbox-api.paddle.com"

    def public_settings(self):
        return {
            "enabled": self.enabled,
            "configured": self.configured,
            "supabaseUrl": self.supabase_url if self.enabled else "",
            "supabaseAnonKey": self.supabase_anon_key if self.enabled else "",
            "paddleClientToken": self.paddle_client_token if self.enabled else "",
            "paddleEnvironment": self.paddle_environment,
            "priceId": self.paddle_price_id if self.enabled else "",
            "annualPriceUsd": ANNUAL_PRICE_USD,
            "accessDays": ACCESS_DAYS,
            "sttMinutesPer30Days": STT_MINUTES_PER_WINDOW,
            "sttMaxJobMinutes": STT_MAX_JOB_SECONDS // 60,
        }


def _request_json(url, method="GET", headers=None, body=None, timeout=15):
    request_headers = {"Accept": "application/json"}
    request_headers.update(headers or {})
    encoded_body = None
    if body is not None:
        encoded_body = json.dumps(body, separators=(",", ":")).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = Request(url, data=encoded_body, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            response_body = response.read()
    except HTTPError as error:
        raise ProviderResponseError(error.code) from error
    except URLError as error:
        raise BillingError("Billing provider is unavailable.") from error
    try:
        return json.loads(response_body.decode("utf-8")) if response_body else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BillingError("Billing provider returned an invalid response.") from error


def _require_config(config):
    if not config.enabled:
        raise BillingError("Online billing is not enabled.")
    if not config.configured:
        raise BillingError("Online billing is enabled but its server configuration is incomplete.")


def authenticate_access_token(config, access_token):
    _require_config(config)
    if not access_token or len(access_token) > 8192:
        raise AuthenticationRequired("Please sign in to continue.")
    try:
        result = _request_json(
            f"{config.supabase_url}/auth/v1/user",
            headers={
                "apikey": config.supabase_anon_key,
                "Authorization": f"Bearer {access_token}",
            },
        )
    except ProviderResponseError as error:
        if error.status_code in (400, 401, 403):
            raise AuthenticationRequired("Your sign-in session has expired. Please sign in again.") from error
        raise
    user_id = result.get("id")
    try:
        user_id = str(uuid.UUID(user_id))
    except (TypeError, ValueError, AttributeError) as error:
        raise AuthenticationRequired("The sign-in session is invalid.") from error
    return {"id": user_id, "email": result.get("email", "")}


def _supabase_rpc(config, function_name, payload):
    _require_config(config)
    return _request_json(
        f"{config.supabase_url}/rest/v1/rpc/{function_name}",
        method="POST",
        headers={
            "apikey": config.supabase_service_role_key,
            "Authorization": f"Bearer {config.supabase_service_role_key}",
        },
        body=payload,
    )


def create_checkout_transaction(config, user_id):
    _require_config(config)
    result = _request_json(
        f"{config.paddle_api_url}/transactions",
        method="POST",
        headers={"Authorization": f"Bearer {config.paddle_api_key}"},
        body={
            "items": [{"price_id": config.paddle_price_id, "quantity": 1}],
            "custom_data": {"supabase_user_id": user_id},
            "collection_mode": "automatic",
            "enable_checkout": True,
        },
    )
    transaction = result.get("data") or {}
    transaction_id = transaction.get("id")
    if not isinstance(transaction_id, str) or not transaction_id.startswith("txn_"):
        raise BillingError("Paddle did not return a checkout transaction.")
    return transaction_id


def verify_paddle_signature(raw_body, signature_header, secret, now=None):
    if not signature_header or not secret:
        return False
    values = {}
    for component in signature_header.split(";"):
        key, separator, value = component.partition("=")
        if separator:
            values.setdefault(key.strip(), []).append(value.strip())
    timestamps = values.get("ts", [])
    signatures = values.get("h1", [])
    if len(timestamps) != 1 or not signatures:
        return False
    try:
        timestamp = int(timestamps[0])
    except ValueError:
        return False
    if abs((int(time.time()) if now is None else now) - timestamp) > 300:
        return False
    signed_payload = timestamps[0].encode("ascii") + b":" + raw_body
    expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, signature) for signature in signatures)


def apply_paddle_event(config, event):
    _require_config(config)
    if not isinstance(event, dict) or not isinstance(event.get("event_id"), str):
        raise BillingError("Paddle webhook payload is invalid.")
    return _supabase_rpc(
        config,
        "apply_paddle_billing_event",
        {
            "p_event_id": event["event_id"],
            "p_event_type": event.get("event_type", ""),
            "p_payload": event,
            "p_expected_price_id": config.paddle_price_id,
        },
    )


def get_billing_status(config, user_id):
    return _supabase_rpc(
        config,
        "get_voice_billing_status",
        {
            "p_user_id": user_id,
            "p_monthly_minutes": STT_MINUTES_PER_WINDOW,
            "p_window_days": STT_WINDOW_DAYS,
        },
    )


def reserve_stt_minutes(config, user_id, duration_seconds, request_id):
    return _supabase_rpc(
        config,
        "reserve_voice_stt_minutes",
        {
            "p_user_id": user_id,
            "p_duration_seconds": duration_seconds,
            "p_request_id": request_id,
            "p_monthly_minutes": STT_MINUTES_PER_WINDOW,
            "p_window_days": STT_WINDOW_DAYS,
            "p_max_job_seconds": STT_MAX_JOB_SECONDS,
        },
    )


def finish_stt_usage(config, request_id, duration_seconds, success):
    return _supabase_rpc(
        config,
        "finish_voice_stt_usage",
        {
            "p_request_id": request_id,
            "p_duration_seconds": duration_seconds,
            "p_success": bool(success),
        },
    )
