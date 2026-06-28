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
