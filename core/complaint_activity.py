from django.contrib.auth import get_user_model

from core.models import Complaint, ComplaintActivity

User = get_user_model()


def log_complaint_activity(
    *,
    complaint: Complaint,
    action: str,
    detail: str = "",
    actor: User | None = None,
) -> ComplaintActivity:
    return ComplaintActivity.objects.create(
        complaint=complaint,
        action=action,
        detail=detail,
        actor=actor,
    )
