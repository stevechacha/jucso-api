from django.contrib.auth import authenticate, get_user_model
from rest_framework import status
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import UserRole
from core.serializers import UserSerializer

User = get_user_model()

STAFF_ROLES = frozenset({UserRole.MINISTER, UserRole.EXECUTIVE, UserRole.ADMIN})
INVALID_CREDENTIALS = "Invalid credentials. Check your ID number and password."


def build_token_response(user, *, status_code: int = status.HTTP_200_OK) -> Response:
    refresh = RefreshToken.for_user(user)
    return Response(
        {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": UserSerializer(user).data,
        },
        status=status_code,
    )


def authenticate_portal_user(*, reg_number: str, password: str, portal: str) -> tuple[User | None, str | None]:
    """
    Authenticate a portal user. Returns (user, error_message).
    Error messages are intentionally generic where possible to avoid account enumeration.
    """
    try:
        user = User.objects.get(reg_number=reg_number)
    except User.DoesNotExist:
        return None, INVALID_CREDENTIALS

    if portal == "student" and user.role != UserRole.STUDENT:
        return None, "This account uses the Staff Portal. Please sign in there."

    if portal == "staff" and user.role not in STAFF_ROLES:
        return None, "This account uses the Student Portal. Please sign in there."

    authenticated = authenticate(username=user.username, password=password)
    if not authenticated:
        return None, INVALID_CREDENTIALS

    return authenticated, None
