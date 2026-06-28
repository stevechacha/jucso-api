from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q
from rest_framework import generics, status, views
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from core.auth import authenticate_portal_user, build_token_response
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
    UserRole,
)
from core.permissions import IsAdminRole, IsLeader, IsStudent
from core.querysets import complaints_for_user, suggestions_for_user
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
    MinistrySerializer,
    NewsItemSerializer,
    StaffCreateSerializer,
    StudentRegisterSerializer,
    SuggestionCreateSerializer,
    SuggestionSerializer,
    UserSerializer,
)
from core.services import create_complaint, create_portal_user
from core.throttling import AuthRateThrottle

User = get_user_model()


class HealthView(views.APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({"status": "ok", "service": "jucso-api"})


class RootView(views.APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response(
            {
                "status": "ok",
                "service": "jucso-api",
                "message": "JUCSO Student Union API",
                "version": "1.0.0",
                "endpoints": {
                    "health": "/api/health/",
                    "login": "/api/auth/login/",
                    "register": "/api/auth/register/",
                    "docs": "/admin/",
                },
            }
        )


class LoginView(views.APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user, error = authenticate_portal_user(
            reg_number=serializer.validated_data["reg_number"],
            password=serializer.validated_data["password"],
            portal=serializer.validated_data["portal"],
        )
        if error:
            return Response({"detail": error}, status=status.HTTP_401_UNAUTHORIZED)

        return build_token_response(user)


class MeView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class StudentRegisterView(views.APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        serializer = StudentRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = create_portal_user(
            reg_number=data["reg_number"],
            first_name=data["first_name"],
            last_name=data["last_name"],
            email=data["email"],
            password=data["password"],
            role=UserRole.STUDENT,
            phone_number=data.get("phone_number", ""),
        )

        return build_token_response(user, status_code=status.HTTP_201_CREATED)


class MinistryListView(generics.ListAPIView):
    serializer_class = MinistrySerializer
    permission_classes = [IsAuthenticated, IsAdminRole]
    queryset = Ministry.objects.all().order_by("name")


class AdminStaffCreateView(views.APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request):
        serializer = StaffCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = create_portal_user(
            reg_number=data["reg_number"],
            first_name=data["first_name"],
            last_name=data["last_name"],
            email=data["email"],
            password=data["password"],
            role=data["role"],
            ministry=data.get("ministry", ""),
            phone_number=data.get("phone_number", ""),
        )

        return Response(AdminUserSerializer(user).data, status=status.HTTP_201_CREATED)


class ComplaintListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ComplaintCreateSerializer
        return ComplaintSerializer

    def get_queryset(self):
        return complaints_for_user(self.request.user)

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsStudent()]
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        complaint = create_complaint(
            student=request.user,
            category=serializer.validated_data["category"],
            description=serializer.validated_data["description"],
            urgent=serializer.validated_data.get("urgent", False),
            supporting_document=serializer.validated_data.get("supporting_document"),
        )
        return Response(ComplaintSerializer(complaint).data, status=status.HTTP_201_CREATED)


class ComplaintDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    lookup_field = "tracking_id"
    lookup_url_kwarg = "tracking_id"

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return ComplaintUpdateSerializer
        return ComplaintSerializer

    def get_queryset(self):
        return complaints_for_user(self.request.user)

    def get_permissions(self):
        if self.request.method in ("PUT", "PATCH"):
            return [IsAuthenticated(), IsLeader()]
        return super().get_permissions()


class SuggestionListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return SuggestionCreateSerializer
        return SuggestionSerializer

    def get_queryset(self):
        return suggestions_for_user(self.request.user)

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsStudent()]
        return super().get_permissions()

    def perform_create(self, serializer):
        return Suggestion.objects.create(student=self.request.user, **serializer.validated_data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        suggestion = self.perform_create(serializer)
        return Response(SuggestionSerializer(suggestion).data, status=status.HTTP_201_CREATED)


class ClubListView(generics.ListAPIView):
    serializer_class = ClubSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return Club.objects.filter(is_active=True).order_by("name")


class ClubJoinView(views.APIView):
    permission_classes = [IsAuthenticated, IsStudent]

    @transaction.atomic
    def post(self, request, pk: int):
        try:
            club = Club.objects.select_for_update().get(pk=pk, is_active=True)
        except Club.DoesNotExist:
            return Response({"detail": "Club not found."}, status=status.HTTP_404_NOT_FOUND)

        membership = ClubMembership.objects.filter(club=club, student=request.user).first()
        if membership:
            membership.delete()
            club.members_count = max(0, club.members_count - 1)
            club.save(update_fields=["members_count"])
            joined = False
        else:
            ClubMembership.objects.create(club=club, student=request.user)
            club.members_count += 1
            club.save(update_fields=["members_count"])
            joined = True

        club.refresh_from_db()
        return Response(ClubSerializer(club, context={"request": request}).data | {"joined": joined})


class EventListView(generics.ListAPIView):
    serializer_class = EventSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return Event.objects.filter(is_active=True).order_by("event_date")


class EventRegisterView(views.APIView):
    permission_classes = [IsAuthenticated, IsStudent]

    @transaction.atomic
    def post(self, request, pk: int):
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
        qs = NewsItem.objects.filter(is_published=True).order_by("-published_at")
        tag = self.request.query_params.get("tag")
        if tag and tag != "All":
            qs = qs.filter(tag=tag)
        return qs


class DocumentListView(generics.ListAPIView):
    serializer_class = DocumentSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return Document.objects.filter(is_published=True).order_by("-published_at")


class ContactCreateView(generics.CreateAPIView):
    serializer_class = ContactMessageSerializer
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]


class ExecutiveStatsView(views.APIView):
    permission_classes = [IsAuthenticated, IsLeader]

    def get(self, request):
        complaints = Complaint.objects.all()
        ministries = Ministry.objects.annotate(
            total=Count("complaints"),
            pending=Count("complaints", filter=Q(complaints__status=ComplaintStatus.PENDING)),
            resolved=Count("complaints", filter=Q(complaints__status=ComplaintStatus.RESOLVED)),
        ).order_by("name")

        ministry_stats = [
            {
                "name": ministry.name,
                "total": ministry.total,
                "pending": ministry.pending,
                "resolved": ministry.resolved,
                "rate": round((ministry.resolved / ministry.total) * 100) if ministry.total else 0,
            }
            for ministry in ministries
        ]

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
        return User.objects.all().order_by("reg_number")


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
                "registered_students": User.objects.filter(role=UserRole.STUDENT).count(),
            }
        )
