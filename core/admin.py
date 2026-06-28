from django.contrib import admin
from django.contrib.auth import get_user_model

from core.models import (
    Club,
    ClubMembership,
    Complaint,
    ContactMessage,
    Document,
    Event,
    EventRegistration,
    Ministry,
    NewsItem,
    Suggestion,
)

User = get_user_model()

admin.site.register(User)
admin.site.register(Ministry)
admin.site.register(Complaint)
admin.site.register(Suggestion)
admin.site.register(Club)
admin.site.register(ClubMembership)
admin.site.register(Event)
admin.site.register(EventRegistration)
admin.site.register(NewsItem)
admin.site.register(Document)
admin.site.register(ContactMessage)
