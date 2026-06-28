from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import generics, status, views
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
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
from core.permissions import AUTHENTICATED, IsAdminRole, IsLeader, IsStudent, PortalAccessPermission
from core.querysets import complaints_for_user, suggestions_for_user
from core.serializers import (
    AdminClubCreateSerializer,
    AdminContactMessageSerializer,
    AdminDocumentCreateSerializer,
    AdminEventCreateSerializer,
    AdminNewsCreateSerializer,
    AdminNewsUpdateSerializer,
    AdminUserSerializer,
    AdminUserUpdateSerializer,
    ClubSerializer,
    ChangePasswordSerializer,
    ComplaintCreateSerializer,
    ComplaintSerializer,
    ComplaintUpdateSerializer,
    ContactMessageSerializer,
    DocumentSerializer,
    EventSerializer,
    LoginSerializer,
    MinistrySerializer,
    NewsItemSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    StaffCreateSerializer,
    StudentRegisterSerializer,
    SuggestionCreateSerializer,
    SuggestionSerializer,
    SuggestionUpdateSerializer,
    UserSerializer,
)
from core.services import create_complaint, create_portal_user
from core.notifications import send_complaint_update_email
from core.password_reset import RESET_MESSAGE, find_user_for_reset, reset_password_with_token, send_password_reset_email
from core.storage import StorageError, get_storage
from core.throttling import AuthRateThrottle

User = get_user_model()


def _format_file_size(num_bytes: int) -> str:
    if num_bytes >= 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.1f} MB"
    return f"{max(1, num_bytes // 1024)} KB"


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
    permission_classes = [*AUTHENTICATED]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class ChangePasswordView(views.APIView):
    permission_classes = [*AUTHENTICATED]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"user": request.user})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if not request.user.check_password(data["current_password"]):
            return Response({"detail": "Current password is incorrect."}, status=status.HTTP_400_BAD_REQUEST)

        request.user.set_password(data["new_password"])
        request.user.must_change_password = False
        request.user.save(update_fields=["password", "must_change_password"])

        return Response({"detail": "Password updated successfully.", "user": UserSerializer(request.user).data})


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


class PasswordResetRequestView(views.APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = find_user_for_reset(email=data.get("email", ""), reg_number=data.get("reg_number", ""))
        if user and user.email:
            send_password_reset_email(user)

        return Response({"detail": RESET_MESSAGE})


class PasswordResetConfirmView(views.APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            reset_password_with_token(
                uid=data["uid"],
                token=data["token"],
                password=data["password"],
            )
        except ValueError:
            return Response(
                {"detail": "Invalid or expired reset link. Request a new password reset."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"detail": "Password updated. You can sign in with your new password."})


class MinistryListView(generics.ListAPIView):
    serializer_class = MinistrySerializer
    permission_classes = [*AUTHENTICATED, IsLeader]
    queryset = Ministry.objects.all().order_by("name")


class AdminStaffCreateView(views.APIView):
    permission_classes = [*AUTHENTICATED, IsAdminRole]

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
            must_change_password=True,
        )

        return Response(AdminUserSerializer(user).data, status=status.HTTP_201_CREATED)


class ComplaintListCreateView(generics.ListCreateAPIView):
    permission_classes = [*AUTHENTICATED]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ComplaintCreateSerializer
        return ComplaintSerializer

    def get_queryset(self):
        return complaints_for_user(self.request.user)

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), PortalAccessPermission(), IsStudent()]
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        supporting_document_path = ""
        uploaded = data.get("supporting_document")
        if uploaded:
            try:
                storage = get_storage()
                folder = f"complaints/{request.user.reg_number.replace('/', '-')}"
                supporting_document_path = storage.upload(
                    folder=folder,
                    original_name=uploaded.name,
                    file_obj=uploaded,
                    content_type=getattr(uploaded, "content_type", None),
                )
            except StorageError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        complaint = create_complaint(
            student=request.user,
            category=data["category"],
            description=data["description"],
            urgent=data.get("urgent", False),
            supporting_document_path=supporting_document_path,
        )
        return Response(
            ComplaintSerializer(complaint, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class ComplaintDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [*AUTHENTICATED]
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
            return [IsAuthenticated(), PortalAccessPermission(), IsLeader()]
        return super().get_permissions()

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        old_status = instance.status
        old_response = instance.response
        old_ministry = instance.ministry_id

        serializer = ComplaintUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if "status" in data:
            instance.status = data["status"]
        if "response" in data:
            instance.response = data["response"]
        if data.get("ministry"):
            instance.ministry = Ministry.objects.get(name=data["ministry"])
            instance.status = ComplaintStatus.PENDING

        instance.save()
        instance.refresh_from_db()

        changed = (
            instance.status != old_status
            or instance.response != old_response
            or instance.ministry_id != old_ministry
        )
        if changed:
            send_complaint_update_email(instance)

        return Response(ComplaintSerializer(instance, context={"request": request}).data)


class SuggestionListCreateView(generics.ListCreateAPIView):
    permission_classes = [*AUTHENTICATED]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return SuggestionCreateSerializer
        return SuggestionSerializer

    def get_queryset(self):
        return suggestions_for_user(self.request.user)

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), PortalAccessPermission(), IsStudent()]
        return super().get_permissions()

    def perform_create(self, serializer):
        return Suggestion.objects.create(student=self.request.user, **serializer.validated_data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        suggestion = self.perform_create(serializer)
        return Response(SuggestionSerializer(suggestion).data, status=status.HTTP_201_CREATED)


class SuggestionDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [*AUTHENTICATED]
    lookup_field = "pk"
    lookup_url_kwarg = "pk"

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return SuggestionUpdateSerializer
        return SuggestionSerializer

    def get_queryset(self):
        return suggestions_for_user(self.request.user)

    def get_permissions(self):
        if self.request.method in ("PUT", "PATCH"):
            return [IsAuthenticated(), PortalAccessPermission(), IsLeader()]
        return super().get_permissions()

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(SuggestionSerializer(instance).data)


class ClubListView(generics.ListAPIView):
    serializer_class = ClubSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return Club.objects.filter(is_active=True).order_by("name")


class ClubJoinView(views.APIView):
    permission_classes = [*AUTHENTICATED, IsStudent]

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
    permission_classes = [*AUTHENTICATED, IsStudent]

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
    permission_classes = [*AUTHENTICATED, IsLeader]

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
    permission_classes = [*AUTHENTICATED, IsAdminRole]

    def get_queryset(self):
        return User.objects.all().order_by("reg_number")


class AdminUserUpdateView(views.APIView):
    permission_classes = [*AUTHENTICATED, IsAdminRole]

    def patch(self, request, reg_number: str):
        reg_number = reg_number.strip("/")
        try:
            user = User.objects.get(reg_number=reg_number)
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = AdminUserUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        is_active = serializer.validated_data["is_active"]

        if user.pk == request.user.pk and not is_active:
            return Response({"detail": "You cannot deactivate your own account."}, status=status.HTTP_400_BAD_REQUEST)

        user.is_active = is_active
        user.save(update_fields=["is_active"])
        return Response(AdminUserSerializer(user).data)


class AdminDocumentCreateView(views.APIView):
    permission_classes = [*AUTHENTICATED, IsAdminRole]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = AdminDocumentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        uploaded = data["file"]

        try:
            storage_path = get_storage().upload(
                folder="documents",
                original_name=uploaded.name,
                file_obj=uploaded,
                content_type=getattr(uploaded, "content_type", None),
            )
        except StorageError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        extension = uploaded.name.rsplit(".", 1)[-1].upper() if "." in uploaded.name else "FILE"
        document = Document.objects.create(
            name=data["name"],
            storage_path=storage_path,
            file_type=(data.get("file_type") or extension)[:20],
            file_size=_format_file_size(uploaded.size),
            published_at=data.get("published_at") or timezone.localdate(),
            is_published=True,
        )
        return Response(
            DocumentSerializer(document, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class AdminNewsCreateView(views.APIView):
    permission_classes = [*AUTHENTICATED, IsAdminRole]

    def post(self, request):
        serializer = AdminNewsCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        item = NewsItem.objects.create(
            title=data["title"],
            excerpt=data["excerpt"],
            tag=data["tag"],
            published_at=data.get("published_at") or timezone.localdate(),
            is_published=True,
        )
        return Response(
            NewsItemSerializer(item).data,
            status=status.HTTP_201_CREATED,
        )


class AdminNewsDetailView(views.APIView):
    permission_classes = [*AUTHENTICATED, IsAdminRole]

    def patch(self, request, pk: int):
        try:
            item = NewsItem.objects.get(pk=pk)
        except NewsItem.DoesNotExist:
            return Response({"detail": "News item not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = AdminNewsUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(item, field, value)
        item.save()
        return Response(NewsItemSerializer(item).data)

    def delete(self, request, pk: int):
        try:
            item = NewsItem.objects.get(pk=pk)
        except NewsItem.DoesNotExist:
            return Response({"detail": "News item not found."}, status=status.HTTP_404_NOT_FOUND)
        item.is_published = False
        item.save(update_fields=["is_published"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminDocumentDetailView(views.APIView):
    permission_classes = [*AUTHENTICATED, IsAdminRole]

    def delete(self, request, pk: int):
        try:
            document = Document.objects.get(pk=pk)
        except Document.DoesNotExist:
            return Response({"detail": "Document not found."}, status=status.HTTP_404_NOT_FOUND)
        document.is_published = False
        document.save(update_fields=["is_published"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminContactMessageListView(generics.ListAPIView):
    serializer_class = AdminContactMessageSerializer
    permission_classes = [*AUTHENTICATED, IsAdminRole]
    queryset = ContactMessage.objects.all().order_by("-created_at")


class AdminClubCreateView(views.APIView):
    permission_classes = [*AUTHENTICATED, IsAdminRole]

    def post(self, request):
        serializer = AdminClubCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        club = Club.objects.create(
            name=data["name"],
            description=data["description"],
            leader=data["leader"],
            category=data["category"],
            is_active=True,
        )
        return Response(ClubSerializer(club, context={"request": request}).data, status=status.HTTP_201_CREATED)


class AdminEventCreateView(views.APIView):
    permission_classes = [*AUTHENTICATED, IsAdminRole]

    def post(self, request):
        serializer = AdminEventCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        event = Event.objects.create(
            title=data["title"],
            description=data["description"],
            location=data["location"],
            event_date=data["event_date"],
            capacity=data["capacity"],
            is_active=True,
        )
        return Response(EventSerializer(event, context={"request": request}).data, status=status.HTTP_201_CREATED)


class AdminOverviewView(views.APIView):
    permission_classes = [*AUTHENTICATED, IsAdminRole]

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
