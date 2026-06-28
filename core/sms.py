import base64
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)


def is_sms_enabled() -> bool:
    return bool(
        getattr(settings, "SMS_ENABLED", False)
        and getattr(settings, "SMS_API_KEY", "")
        and getattr(settings, "SMS_USERNAME", "")
    )


def normalize_phone(phone: str) -> str:
    cleaned = "".join(ch for ch in phone.strip() if ch.isdigit() or ch == "+")
    if not cleaned:
        return ""
    if cleaned.startswith("+"):
        return cleaned
    if cleaned.startswith("0"):
        return f"+255{cleaned[1:]}"
    if cleaned.startswith("255"):
        return f"+{cleaned}"
    return f"+{cleaned}"


def send_sms(to: str, message: str) -> bool:
    phone = normalize_phone(to)
    if not phone:
        return False

    if not is_sms_enabled():
        logger.info("SMS skipped (not configured): to=%s", phone)
        return False

    provider = getattr(settings, "SMS_PROVIDER", "africas_talking")
    if provider == "africas_talking":
        return _send_africas_talking(phone, message[:160])
    logger.warning("Unknown SMS provider: %s", provider)
    return False


def _send_africas_talking(to: str, message: str) -> bool:
    username = settings.SMS_USERNAME
    api_key = settings.SMS_API_KEY
    payload = {
        "username": username,
        "to": to,
        "message": message,
    }
    sender_id = getattr(settings, "SMS_SENDER_ID", "")
    if sender_id:
        payload["from"] = sender_id

    request = urllib.request.Request(
        "https://api.africastalking.com/version1/messaging",
        data=urllib.parse.urlencode(payload).encode(),
        method="POST",
    )
    credentials = base64.b64encode(f"{username}:{api_key}".encode()).decode()
    request.add_header("Authorization", f"Basic {credentials}")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    request.add_header("Accept", "application/json")

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return 200 <= response.status < 300
    except urllib.error.URLError as exc:
        logger.warning("SMS delivery failed: %s", exc)
        return False
