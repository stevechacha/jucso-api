from core.models import CATEGORY_TO_MINISTRY, ComplaintCategory


def ministry_name_for_category(category: str) -> str:
    try:
        enum_value = ComplaintCategory(category)
        return CATEGORY_TO_MINISTRY[enum_value]
    except ValueError:
        return CATEGORY_TO_MINISTRY[ComplaintCategory.OTHER]


def next_tracking_id() -> str:
    from core.models import Complaint

    last = Complaint.objects.order_by("-id").first()
    next_num = (last.id + 1) if last else 1
    return f"JUC-{next_num:03d}"


def username_from_reg(reg_number: str) -> str:
    return reg_number.strip().lower().replace("/", "-").replace(" ", "-")


def create_portal_user(
    *,
    reg_number: str,
    first_name: str,
    last_name: str,
    email: str,
    password: str,
    role: str,
    ministry: str = "",
    phone_number: str = "",
):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return User.objects.create_user(
        username=username_from_reg(reg_number),
        reg_number=reg_number.strip(),
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        email=email.strip().lower(),
        password=password,
        role=role,
        ministry=ministry.strip(),
        phone_number=phone_number.strip(),
    )
