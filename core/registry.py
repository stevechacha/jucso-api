import csv
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from django.conf import settings


class RegistryError(Exception):
    pass


def registry_enabled() -> bool:
    return bool(getattr(settings, "STUDENT_REGISTRY_API_URL", "").strip() or getattr(settings, "STUDENT_REGISTRY_CSV", "").strip())


def _csv_registry_rows() -> dict[str, dict[str, str]]:
    csv_path = getattr(settings, "STUDENT_REGISTRY_CSV", "").strip()
    if not csv_path:
        return {}

    path = Path(csv_path)
    if not path.is_file():
        return {}

    rows: dict[str, dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            reg = (row.get("reg_number") or row.get("reg") or "").strip()
            if reg:
                rows[reg.upper()] = {k: (v or "").strip() for k, v in row.items()}
    return rows


def _verify_via_csv(*, reg_number: str, email: str, first_name: str, last_name: str) -> tuple[bool, str]:
    rows = _csv_registry_rows()
    if not rows:
        return False, "Student registry file is not available."

    record = rows.get(reg_number.strip().upper())
    if not record:
        return False, "This registration number is not in the college student registry."

    record_email = (record.get("email") or "").lower()
    if record_email and email and record_email != email.lower():
        return False, "Email does not match the college registry record for this registration number."

    record_first = (record.get("first_name") or record.get("firstname") or "").lower()
    record_last = (record.get("last_name") or record.get("lastname") or "").lower()
    if record_first and first_name and record_first != first_name.strip().lower():
        return False, "First name does not match the college registry record."
    if record_last and last_name and record_last != last_name.strip().lower():
        return False, "Last name does not match the college registry record."

    return True, ""


def _verify_via_api(*, reg_number: str, email: str, first_name: str, last_name: str) -> tuple[bool, str]:
    base_url = getattr(settings, "STUDENT_REGISTRY_API_URL", "").strip().rstrip("/")
    if not base_url:
        return True, ""

    params = urllib.parse.urlencode(
        {
            "reg_number": reg_number.strip(),
            "email": email.strip(),
            "first_name": first_name.strip(),
            "last_name": last_name.strip(),
        }
    )
    url = f"{base_url}?{params}"
    headers = {"Accept": "application/json"}
    api_key = getattr(settings, "STUDENT_REGISTRY_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False, "This registration number is not in the college student registry."
        return False, "Could not verify registration number with the college registry."
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return False, "College registry service is unavailable. Try again later."

    if isinstance(payload, dict) and payload.get("valid") is False:
        message = payload.get("detail") or payload.get("message")
        return False, message or "Registration could not be verified."

    return True, ""


def verify_student_registry(*, reg_number: str, email: str = "", first_name: str = "", last_name: str = "") -> tuple[bool, str]:
    if not registry_enabled():
        return True, ""

    api_url = getattr(settings, "STUDENT_REGISTRY_API_URL", "").strip()
    if api_url:
        return _verify_via_api(reg_number=reg_number, email=email, first_name=first_name, last_name=last_name)

    return _verify_via_csv(reg_number=reg_number, email=email, first_name=first_name, last_name=last_name)
