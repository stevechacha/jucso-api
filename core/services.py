from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.complaint_activity import log_complaint_activity
from core.models import CATEGORY_TO_MINISTRY, Complaint, ComplaintCategory, Ministry, UserRole

CONFIDENTIAL_CATEGORIES = frozenset({ComplaintCategory.HEALTH})


def ministry_name_for_category(category: str) -> str:
    try:
        enum_value = ComplaintCategory(category)
        return CATEGORY_TO_MINISTRY[enum_value]
    except ValueError:
        return CATEGORY_TO_MINISTRY[ComplaintCategory.OTHER]


def ministry_slug_for_name(name: str) -> str:
    return name.lower().replace(" ", "-").replace("&", "and")


@transaction.atomic
def create_complaint(
    *,
    student,
    category: str,
    description: str,
    urgent: bool = False,
    supporting_document_path: str = "",
) -> Complaint:
    ministry_name = ministry_name_for_category(category)
    ministry, _ = Ministry.objects.get_or_create(
        name=ministry_name,
        defaults={"slug": ministry_slug_for_name(ministry_name)},
    )

    last = Complaint.objects.select_for_update().order_by("-id").first()
    next_num = (last.id + 1) if last else 1
    tracking_id = f"JUC-{next_num:03d}"

    sla_days = getattr(settings, "COMPLAINT_SLA_DAYS", 7)
    due_at = timezone.now() + timedelta(days=sla_days)

    complaint = Complaint.objects.create(
        tracking_id=tracking_id,
        student=student,
        ministry=ministry,
        category=category,
        description=description,
        urgent=urgent,
        is_confidential=category in {c.value for c in CONFIDENTIAL_CATEGORIES},
        supporting_document_path=supporting_document_path,
        due_at=due_at,
    )
    log_complaint_activity(
        complaint=complaint,
        action="Submitted",
        detail=f"Routed to {ministry.name}",
        actor=student,
    )
    return complaint


def username_from_reg(reg_number: str) -> str:
    return reg_number.strip().lower().replace("/", "-").replace(" ", "-")


@transaction.atomic
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
    must_change_password: bool = False,
):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    email_verified = role != UserRole.STUDENT
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
        must_change_password=must_change_password,
        email_verified=email_verified,
    )
