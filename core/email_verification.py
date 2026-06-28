from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

User = get_user_model()


def verification_token_for_user(user: User) -> tuple[str, str]:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return uid, token


def send_email_verification(user: User) -> None:
    if not user.email or user.email_verified:
        return

    uid, token = verification_token_for_user(user)
    frontend = settings.FRONTEND_URL.rstrip("/")
    verify_url = f"{frontend}/verify-email?uid={uid}&token={token}"

    send_mail(
        "Verify your JUCSO portal email",
        "\n".join(
            [
                f"Hello {user.display_name},",
                "",
                "Welcome to the JUCSO Digital Portal. Please verify your email address:",
                verify_url,
                "",
                "If you did not register, you can ignore this message.",
                "",
                "— JUCSO Digital Portal",
            ]
        ),
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=True,
    )


def verify_email_with_token(*, uid: str, token: str) -> User:
    try:
        user_id = force_str(urlsafe_base64_decode(uid))
        user = User.objects.get(pk=user_id)
    except (User.DoesNotExist, ValueError, OverflowError):
        raise ValueError("Invalid verification link.") from None

    if user.email_verified:
        return user

    if not default_token_generator.check_token(user, token):
        raise ValueError("Invalid or expired verification link.")

    user.email_verified = True
    user.save(update_fields=["email_verified"])
    return user
