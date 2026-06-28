from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    """Normalize API errors to a consistent `{ detail: ... }` shape."""
    response = exception_handler(exc, context)
    if response is None:
        return response

    data = response.data
    if isinstance(data, dict) and "detail" in data:
        return response

    if isinstance(data, dict):
        if "non_field_errors" in data:
            detail = data["non_field_errors"]
        else:
            detail = data
        response.data = {"detail": detail, "errors": data}
        return response

    response.data = {"detail": data}
    return response
