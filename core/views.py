from django.contrib.auth import authenticate, get_user_model
from django.db import transaction
from django.db.models import Count, Q
from rest_framework import generics, status, views
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import (
    Club,
    ClubMembership,
    Complaint,
    ComplaintStatus,
    ContactMessage,
    Document,
    Event,
    EventRegistration,
    Ministry,
    NewsItem,
    Suggestion,
)
from core.permissions import IsAdminRole, IsLeader
from core.serializers import (
    AdminUserSerializer,
    ClubSerializer,
    ComplaintCreateSerializer,
    ComplaintSerializer,
    ComplaintUpdateSerializer,
    ContactMessageSerializer,
    DocumentSerializer,
    EventSerializer,
    LoginSerializer,
    NewsItemSerializer,
    SuggestionCreateSerializer,
    SuggestionSerializer,
    UserSerializer,
)
from core.services import ministry_name_for_category, next_tracking_id

User = get_user_model()


class HealthView(views.APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok", "service": "jucso-api"})


class LoginView(views.APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reg_number = serializer.validated_data["reg_number"].strip()
        password = serializer.validated_data["password"]
        role = serializer.validated_data["role"]

        try:
            user = User.objects.get(reg_number=reg_number)
        except User.DoesNotExist:
            return Response({"detail": "Registration number not found."}, status=status.HTTP_401_UNAUTHORIZED)

        if user.role != role:
            return Response(
                {"detail": f"This account is not a {role} account. Select role: \"{user.role}\"."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        authenticated = authenticate(request, username=user.username, password=password)
        if not authenticated:
            return Response({"detail": "Invalid password."}, status=status.HTTP_401_UNAUTHORIZED)

        refresh = RefreshToken.for_user(authenticated)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(authenticated).data,
            }
        )


class MeView(views.APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class ComplaintListCreateView(generics.ListCreateAPIView):
    def get_serializer_class(self):
        if self.request.method == "POST":
            return ComplaintCreateSerializer
        return ComplaintSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Complaint.objects.select_related("student", "ministry")

        if user.role == "student":
            return qs.filter(student=user)
        if user.role == "minister":
            return qs.filter(ministry__name=user.ministry)
        return qs

    def perform_create(self, serializer):
        ministry_name = ministry_name_for_category(serializer.validated_data["category"])
        ministry, _ = Ministry.objects.get_or_create(
            name=ministry_name,
            defaults={"slug": ministry_name.lower().replace(" ", "-").replace("&", "and")},
        )
        Complaint.objects.create(
            tracking_id=next_tracking_id(),
            student=self.request.user,
            ministry=ministry,
            **serializer.validated_data,
        )

    def create(self, request, *args, **kwargs):
        if request.user.role != "student":
            return Response({"detail": "Only students can submit complaints."}, status=status.HTTP_403_FORBIDDEN)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        complaint = Complaint.objects.filter(student=request.user).first()
        return Response(ComplaintSerializer(complaint).data, status=status.HTTP_201_CREATED)


class ComplaintDetailView(generics.RetrieveUpdateAPIView):
    lookup_field = "tracking_id"
    lookup_url_kwarg = "tracking_id"

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return ComplaintUpdateSerializer
        return ComplaintSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Complaint.objects.select_related("student", "ministry")
        if user.role == "student":
            return qs.filter(student=user)
        if user.role == "minister":
            return qs.filter(ministry__name=user.ministry)
        return qs

    def get_permissions(self):
        if self.request.method in ("PUT", "PATCH"):
            return [IsAuthenticated(), IsLeader()]
        return [IsAuthenticated()]


class SuggestionListCreateView(generics.ListCreateAPIView):
    def get_serializer_class(self):
        if self.request.method == "POST":
            return SuggestionCreateSerializer
        return SuggestionSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Suggestion.objects.select_related("student")
        if user.role == "student":
            return qs.filter(student=user)
        return qs

    def create(self, request, *args, **kwargs):
        if request.user.role != "student":
            return Response({"detail": "Only students can submit suggestions."}, status=status.HTTP_403_FORBIDDEN)
        serializer = SuggestionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        suggestion = Suggestion.objects.create(student=request.user, **serializer.validated_data)
        return Response(SuggestionSerializer(suggestion).data, status=status.HTTP_201_CREATED)


class ClubListView(generics.ListAPIView):
    serializer_class = ClubSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return Club.objects.filter(is_active=True)


class ClubJoinView(views.APIView):
    def post(self, request, pk: int):
        if request.user.role != "student":
            return Response({"detail": "Only students can join clubs."}, status=status.HTTP_403_FORBIDDEN)

        try:
            club = Club.objects.get(pk=pk, is_active=True)
        except Club.DoesNotExist:
            return Response({"detail": "Club not found."}, status=status.HTTP_404_NOT_FOUND)

        membership, created = ClubMembership.objects.get_or_create(club=club, student=request.user)
        if created:
            club.members_count += 1
            club.save(update_fields=["members_count"])
            joined = True
        else:
            membership.delete()
            club.members_count = max(0, club.members_count - 1)
            club.save(update_fields=["members_count"])
            joined = False

        return Response(ClubSerializer(club, context={"request": request}).data | {"joined": joined})


class EventListView(generics.ListAPIView):
    serializer_class = EventSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return Event.objects.filter(is_active=True)


class EventRegisterView(views.APIView):
    @transaction.atomic
    def post(self, request, pk: int):
        if request.user.role != "student":
            return Response({"detail": "Only students can register for events."}, status=status.HTTP_403_FORBIDDEN)

        try:
            event = Event.objects.select_for_update().get(pk=pk, is_active=True)
        except Event.DoesNotExist:
            return Response({"detail": "Event not found."}, status=status.HTTP_404_NOT_FOUND)

        registration = EventRegistration.objects.filter(event=event, student=request.user).first()
        if registration:
            registration.delete()
            event.registered_count = max(0, event.registered_count - 1)
            event.save(update_fields=["registered_count"])
        else:
            if event.is_full:
                return Response({"detail": "Event is at full capacity."}, status=status.HTTP_400_BAD_REQUEST)
            EventRegistration.objects.create(event=event, student=request.user)
            event.registered_count += 1
            event.save(update_fields=["registered_count"])

        event.refresh_from_db()
        return Response(EventSerializer(event, context={"request": request}).data)


class NewsListView(generics.ListAPIView):
    serializer_class = NewsItemSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        qs = NewsItem.objects.filter(is_published=True)
        tag = self.request.query_params.get("tag")
        if tag and tag != "All":
            qs = qs.filter(tag=tag)
        return qs


class DocumentListView(generics.ListAPIView):
    serializer_class = DocumentSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return Document.objects.filter(is_published=True)


class ContactCreateView(generics.CreateAPIView):
    serializer_class = ContactMessageSerializer
    permission_classes = [AllowAny]


class ExecutiveStatsView(views.APIView):
    permission_classes = [IsAuthenticated, IsLeader]

    def get(self, request):
        complaints = Complaint.objects.all()
        ministries = Ministry.objects.annotate(
            total=Count("complaints"),
            pending=Count("complaints", filter=Q(complaints__status=ComplaintStatus.PENDING)),
            resolved=Count("complaints", filter=Q(complaints__status=ComplaintStatus.RESOLVED)),
        )

        ministry_stats = []
        for m in ministries:
            rate = round((m.resolved / m.total) * 100) if m.total else 0
            ministry_stats.append(
                {
                    "name": m.name,
                    "total": m.total,
                    "pending": m.pending,
                    "resolved": m.resolved,
                    "rate": rate,
                }
            )

        return Response(
            {
                "total_complaints": complaints.count(),
                "urgent": complaints.filter(urgent=True).count(),
                "open_issues": complaints.exclude(status=ComplaintStatus.RESOLVED).count(),
                "resolved": complaints.filter(status=ComplaintStatus.RESOLVED).count(),
                "ministry_stats": ministry_stats,
                "urgent_issues": ComplaintSerializer(
                    complaints.filter(urgent=True).exclude(status=ComplaintStatus.RESOLVED)[:10],
                    many=True,
                ).data,
            }
        )


class AdminUsersView(generics.ListAPIView):
    serializer_class = AdminUserSerializer
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get_queryset(self):
        return User.objects.all()


class AdminOverviewView(views.APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        return Response(
            {
                "total_users": User.objects.count(),
                "total_complaints": Complaint.objects.count(),
                "total_suggestions": Suggestion.objects.count(),
                "active_clubs": Club.objects.filter(is_active=True).count(),
                "upcoming_events": Event.objects.filter(is_active=True).count(),
                "open_complaints": Complaint.objects.exclude(status=ComplaintStatus.RESOLVED).count(),
                "pending_suggestions": Suggestion.objects.exclude(status="Implemented").count(),
                "registered_students": User.objects.filter(role="student").count(),
            }
        )
