from django.contrib.auth import get_user_model
from django.db.models import QuerySet

from core.models import Complaint, Suggestion, UserRole

User = get_user_model()


def complaints_for_user(user: User) -> QuerySet[Complaint]:
    qs = Complaint.objects.select_related("student", "ministry")
    if user.role == UserRole.STUDENT:
        return qs.filter(student=user)
    if user.role == UserRole.MINISTER:
        return qs.filter(ministry__name=user.ministry)
    return qs


def suggestions_for_user(user: User) -> QuerySet[Suggestion]:
    qs = Suggestion.objects.select_related("student")
    if user.role == UserRole.STUDENT:
        return qs.filter(student=user)
    return qs
