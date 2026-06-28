from django.urls import path

from core import views

urlpatterns = [
    path("health/", views.HealthView.as_view(), name="health"),
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("auth/me/", views.MeView.as_view(), name="me"),
    path("complaints/", views.ComplaintListCreateView.as_view(), name="complaint-list"),
    path("complaints/<str:tracking_id>/", views.ComplaintDetailView.as_view(), name="complaint-detail"),
    path("suggestions/", views.SuggestionListCreateView.as_view(), name="suggestion-list"),
    path("clubs/", views.ClubListView.as_view(), name="club-list"),
    path("clubs/<int:pk>/join/", views.ClubJoinView.as_view(), name="club-join"),
    path("events/", views.EventListView.as_view(), name="event-list"),
    path("events/<int:pk>/register/", views.EventRegisterView.as_view(), name="event-register"),
    path("news/", views.NewsListView.as_view(), name="news-list"),
    path("documents/", views.DocumentListView.as_view(), name="document-list"),
    path("contact/", views.ContactCreateView.as_view(), name="contact"),
    path("stats/executive/", views.ExecutiveStatsView.as_view(), name="executive-stats"),
    path("admin/users/", views.AdminUsersView.as_view(), name="admin-users"),
    path("admin/overview/", views.AdminOverviewView.as_view(), name="admin-overview"),
]
