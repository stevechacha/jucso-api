from django.contrib.auth import get_user_model
from django.db.models import Case, IntegerField, QuerySet, Value, When
from django.utils import timezone

from core.models import Complaint, ComplaintStatus, Suggestion, UserRole

User = get_user_model()


def _complaint_priority_order(qs: QuerySet[Complaint]) -> QuerySet[Complaint]:
    now = timezone.now()
    return qs.annotate(
        _priority=Case(
            When(urgent=True, status=ComplaintStatus.RESOLVED, then=Value(3)),
            When(urgent=True, then=Value(0)),
            When(due_at__lt=now, then=Value(1)),
            default=Value(2),
            output_field=IntegerField(),
        )
    ).order_by("_priority", "-date_submitted")


def complaints_for_user(user: User) -> QuerySet[Complaint]:
    qs = Complaint.objects.select_related("student", "ministry").prefetch_related("activities")
    if user.role == UserRole.STUDENT:
        return _complaint_priority_order(qs.filter(student=user))
    if user.role == UserRole.MINISTER:
        return _complaint_priority_order(qs.filter(ministry__name=user.ministry))
    return _complaint_priority_order(qs)


def suggestions_for_user(user: User) -> QuerySet[Suggestion]:
    qs = Suggestion.objects.select_related("student")
    if user.role == UserRole.STUDENT:
        return qs.filter(student=user)
    return qs
