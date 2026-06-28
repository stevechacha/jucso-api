from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

User = get_user_model()

RESET_MESSAGE = (
    "If an account matches those details, password reset instructions have been sent to the registered email."
)


def find_user_for_reset(*, email: str = "", reg_number: str = "") -> User | None:
    if email:
        user = User.objects.filter(email__iexact=email.strip()).first()
        if user:
            return user
    if reg_number:
        return User.objects.filter(reg_number=reg_number.strip()).first()
    return None


def build_reset_link(user: User) -> str:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    frontend = settings.FRONTEND_URL.rstrip("/")
    return f"{frontend}/reset-password?uid={uid}&token={token}"


def send_password_reset_email(user: User) -> None:
    link = build_reset_link(user)
    subject = "Reset your JUCSO portal password"
    message = (
        f"Hello {user.display_name},\n\n"
        f"We received a request to reset your JUCSO portal password.\n\n"
        f"Open this link to choose a new password (valid for 24 hours):\n{link}\n\n"
        f"If you did not request this, you can ignore this email.\n\n"
        f"— JUCSO Digital Portal"
    )
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )


def user_from_reset_uid(uid: str) -> User | None:
    try:
        user_id = force_str(urlsafe_base64_decode(uid))
        return User.objects.get(pk=user_id)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return None


def reset_password_with_token(*, uid: str, token: str, password: str) -> User:
    user = user_from_reset_uid(uid)
    if not user or not default_token_generator.check_token(user, token):
        raise ValueError("Invalid or expired reset link.")
    user.set_password(password)
    user.save(update_fields=["password"])
    return user
