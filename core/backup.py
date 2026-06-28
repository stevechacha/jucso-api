from django.contrib.auth import get_user_model
from django.utils import timezone

from core.models import Club, Complaint, ContactMessage, Document, Event, NewsItem, Suggestion
from core.serializers import (
    AdminContactMessageSerializer,
    ClubSerializer,
    ComplaintSerializer,
    DocumentSerializer,
    EventSerializer,
    NewsItemSerializer,
    SuggestionSerializer,
)

User = get_user_model()


def build_portal_backup() -> dict:
    complaints = Complaint.objects.select_related("student", "ministry").order_by("pk")
    suggestions = Suggestion.objects.select_related("student").order_by("pk")
    users = User.objects.order_by("reg_number")

    return {
        "exported_at": timezone.now().isoformat(),
        "version": 1,
        "counts": {
            "users": users.count(),
            "complaints": complaints.count(),
            "suggestions": suggestions.count(),
            "clubs": Club.objects.filter(is_active=True).count(),
            "events": Event.objects.filter(is_active=True).count(),
            "news": NewsItem.objects.filter(is_published=True).count(),
            "documents": Document.objects.filter(is_published=True).count(),
            "contact_messages": ContactMessage.objects.count(),
        },
        "users": [
            {
                "reg_number": user.reg_number,
                "name": user.display_name,
                "email": user.email,
                "role": user.role,
                "ministry": user.ministry,
                "is_active": user.is_active,
            }
            for user in users
        ],
        "complaints": ComplaintSerializer(complaints, many=True).data,
        "suggestions": SuggestionSerializer(suggestions, many=True).data,
        "clubs": ClubSerializer(Club.objects.filter(is_active=True).order_by("name"), many=True).data,
        "events": EventSerializer(Event.objects.filter(is_active=True).order_by("event_date"), many=True).data,
        "news": NewsItemSerializer(NewsItem.objects.filter(is_published=True).order_by("-published_at"), many=True).data,
        "documents": DocumentSerializer(
            Document.objects.filter(is_published=True).order_by("-published_at"), many=True
        ).data,
        "contact_messages": AdminContactMessageSerializer(
            ContactMessage.objects.order_by("-created_at"), many=True
        ).data,
    }
