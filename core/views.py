from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import generics, status, views
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from core.auth import authenticate_portal_user, build_token_response
from core.backup import build_portal_backup
from core.complaint_activity import log_complaint_activity
from core.email_verification import send_email_verification, verify_email_with_token
from core.models import (
    CATEGORY_TO_MINISTRY,
    Club,
    ClubMembership,
    Complaint,
    ComplaintCategory,
    ComplaintStatus,
    ContactMessage,
    CronJobLog,
    Document,
    Event,
    EventRegistration,
    Ministry,
    NewsItem,
    Suggestion,
    SuggestionStatus,
    UserRole,
)
from core.permissions import AUTHENTICATED, IsAdminRole, IsLeader, IsStudent, PortalAccessPermission
from core.querysets import complaints_for_user, suggestions_for_user
from core.registry import registry_enabled
from core.serializers import (
    AdminClubCreateSerializer,
    AdminClubUpdateSerializer,
    AdminContactMessageSerializer,
    AdminContactMessageUpdateSerializer,
    AdminDocumentCreateSerializer,
    AdminDocumentUpdateSerializer,
    AdminEventCreateSerializer,
    AdminEventUpdateSerializer,
    AdminNewsCreateSerializer,
    AdminNewsUpdateSerializer,
    AdminUserSerializer,
    AdminUserUpdateSerializer,
    ClubSerializer,
    ChangePasswordSerializer,
    ComplaintCreateSerializer,
    ComplaintSerializer,
    ComplaintTrackRequestSerializer,
    ComplaintTrackSerializer,
    ComplaintUpdateSerializer,
    ContactMessageSerializer,
    DocumentSerializer,
    EmailVerifySerializer,
    EventSerializer,
    LoginSerializer,
    LeadershipMemberSerializer,
    MinistrySerializer,
    NewsItemSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    ProfileUpdateSerializer,
    ResendVerificationSerializer,
    StaffCreateSerializer,
    StudentRegisterSerializer,
    SuggestionCreateSerializer,
    SuggestionSerializer,
    SuggestionUpdateSerializer,
    UserSerializer,
)
from core.services import create_complaint, create_portal_user
from core.notifications import (
    notify_complaint_submitted,
    notify_complaint_update,
    notify_contact_message,
    notify_suggestion_update,
)
from core.password_reset import RESET_MESSAGE, find_user_for_reset, reset_password_with_token, send_password_reset_email
from core.storage import StorageError, get_storage
from core.throttling import AuthRateThrottle, ComplaintCreateRateThrottle, ContactRateThrottle, WriteRateThrottle

User = get_user_model()


def _initials_for_name(name: str) -> str:
    parts = [p for p in name.split() if p]
    if not parts:
        return "JU"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return f"{parts[0][0]}{parts[-1][0]}".upper()


def _leadership_role_label(user: User) -> str:
    if user.role == UserRole.MINISTER:
        return f"{user.ministry} Minister" if user.ministry else "Minister"
    if user.role == UserRole.EXECUTIVE:
        return "Executive"
    return user.get_role_display()


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

    def patch(self, request):
        serializer = ProfileUpdateSerializer(data=request.data, partial=True, context={"user": request.user})
        serializer.is_valid(raise_exception=True)
        user = request.user
        for field, value in serializer.validated_data.items():
            setattr(user, field, value)
        user.save()
        return Response(UserSerializer(user).data)


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


class EmailVerifyView(views.APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        serializer = EmailVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            user = verify_email_with_token(uid=data["uid"], token=data["token"])
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Email verified successfully.", "user": UserSerializer(user).data})


class ResendVerificationView(views.APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = None
        if data.get("reg_number"):
            user = User.objects.filter(reg_number=data["reg_number"]).first()
        elif data.get("email"):
            user = User.objects.filter(email__iexact=data["email"]).first()

        if user and user.role == UserRole.STUDENT and not user.email_verified:
            send_email_verification(user)

        return Response({"detail": "If an unverified student account exists, a verification email has been sent."})


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
        send_email_verification(user)

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

    def get_throttles(self):
        if self.request.method == "POST":
            return [ComplaintCreateRateThrottle()]
        return super().get_throttles()

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
        if request.user.role == UserRole.STUDENT and not request.user.email_verified:
            return Response(
                {"detail": "Verify your email before submitting a complaint. Check your inbox or resend verification."},
                status=status.HTTP_403_FORBIDDEN,
            )

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
        notify_complaint_submitted(complaint)
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
            if data["status"] == ComplaintStatus.RESOLVED:
                log_complaint_activity(
                    complaint=instance,
                    action="Resolved",
                    detail=data.get("response") or instance.response,
                    actor=request.user,
                )
            elif data["status"] == ComplaintStatus.IN_PROGRESS:
                log_complaint_activity(
                    complaint=instance,
                    action="In Progress",
                    detail=data.get("response") or "",
                    actor=request.user,
                )
            elif instance.status != old_status:
                log_complaint_activity(
                    complaint=instance,
                    action=f"Status → {data['status']}",
                    detail=data.get("response") or "",
                    actor=request.user,
                )
        if "response" in data and data["response"] != old_response:
            instance.response = data["response"]
            if "status" not in data:
                log_complaint_activity(
                    complaint=instance,
                    action="Response added",
                    detail=data["response"],
                    actor=request.user,
                )
        elif "response" in data:
            instance.response = data["response"]
        if data.get("ministry"):
            new_ministry = Ministry.objects.get(name=data["ministry"])
            if new_ministry.pk != old_ministry:
                log_complaint_activity(
                    complaint=instance,
                    action="Forwarded",
                    detail=f"To {new_ministry.name}",
                    actor=request.user,
                )
            instance.ministry = new_ministry
            instance.status = ComplaintStatus.PENDING

        instance.save()
        instance.refresh_from_db()

        changed = (
            instance.status != old_status
            or instance.response != old_response
            or instance.ministry_id != old_ministry
        )
        if changed:
            notify_complaint_update(instance)

        return Response(ComplaintSerializer(instance, context={"request": request}).data)


class ComplaintTrackView(views.APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        serializer = ComplaintTrackRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            complaint = (
                Complaint.objects.select_related("ministry", "student")
                .prefetch_related("activities")
                .get(
                    tracking_id=data["tracking_id"].strip().upper(),
                    student__reg_number=data["reg_number"].strip(),
                )
            )
        except Complaint.DoesNotExist:
            return Response({"detail": "No complaint found for those details."}, status=status.HTTP_404_NOT_FOUND)
        return Response(ComplaintTrackSerializer(complaint).data)


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
        from datetime import timedelta

        from django.conf import settings
        from django.utils import timezone

        sla_days = getattr(settings, "SUGGESTION_SLA_DAYS", 7)
        return Suggestion.objects.create(
            student=self.request.user,
            due_at=timezone.now() + timedelta(days=sla_days),
            **serializer.validated_data,
        )

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
        old_status = instance.status
        old_response = instance.response or ""
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        instance.refresh_from_db()
        if instance.status != old_status or (instance.response or "") != old_response:
            notify_suggestion_update(instance)
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


class LeadershipListView(views.APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        leaders = User.objects.filter(
            role__in=[UserRole.MINISTER, UserRole.EXECUTIVE],
            is_active=True,
        ).order_by("role", "ministry", "first_name")

        payload = [
            {
                "name": user.display_name,
                "role": _leadership_role_label(user),
                "ministry": user.ministry or "",
                "initials": _initials_for_name(user.display_name),
            }
            for user in leaders
        ]
        return Response(LeadershipMemberSerializer(payload, many=True).data)


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
    throttle_classes = [ContactRateThrottle]

    def perform_create(self, serializer):
        message = serializer.save()
        notify_contact_message(message)


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

        now = timezone.now()
        week_start = now - timedelta(days=7)
        open_qs = complaints.exclude(status=ComplaintStatus.RESOLVED)
        return Response(
            {
                "total_complaints": complaints.count(),
                "urgent": complaints.filter(urgent=True).count(),
                "open_issues": open_qs.count(),
                "resolved": complaints.filter(status=ComplaintStatus.RESOLVED).count(),
                "overdue": open_qs.filter(due_at__lt=now).count(),
                "resolved_this_week": complaints.filter(
                    status=ComplaintStatus.RESOLVED,
                    updated_at__gte=week_start,
                ).count(),
                "ministry_stats": ministry_stats,
                "urgent_issues": ComplaintSerializer(
                    complaints.filter(urgent=True).exclude(status=ComplaintStatus.RESOLVED)[:10],
                    many=True,
                ).data,
            }
        )


class MinisterWorkloadView(views.APIView):
    permission_classes = [*AUTHENTICATED, IsLeader]

    def get(self, request):
        if request.user.role != UserRole.MINISTER:
            return Response({"detail": "Ministers only."}, status=status.HTTP_403_FORBIDDEN)

        now = timezone.now()
        week_start = now - timedelta(days=7)
        qs = complaints_for_user(request.user)
        open_qs = qs.exclude(status=ComplaintStatus.RESOLVED)

        return Response(
            {
                "open_count": open_qs.count(),
                "resolved_this_week": qs.filter(status=ComplaintStatus.RESOLVED, updated_at__gte=week_start).count(),
                "overdue_count": open_qs.filter(due_at__lt=now).count(),
                "urgent_open": open_qs.filter(urgent=True).count(),
                "pending": open_qs.filter(status=ComplaintStatus.PENDING).count(),
                "in_progress": open_qs.filter(status=ComplaintStatus.IN_PROGRESS).count(),
            }
        )


class ComplaintCategoriesView(views.APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response(
            [
                {"category": category.value, "ministry": CATEGORY_TO_MINISTRY[category]}
                for category in ComplaintCategory
            ]
        )


class PublicStatsView(views.APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        total = Complaint.objects.count()
        resolved = Complaint.objects.filter(status=ComplaintStatus.RESOLVED).count()
        all_suggestions = Suggestion.objects.all()
        total_suggestions = all_suggestions.count()
        implemented_suggestions = all_suggestions.filter(status=SuggestionStatus.IMPLEMENTED).count()
        return Response(
            {
                "students_registered": User.objects.filter(role=UserRole.STUDENT, is_active=True).count(),
                "ministries": Ministry.objects.count(),
                "resolution_rate": round((resolved / total) * 100) if total else 0,
                "active_clubs": Club.objects.filter(is_active=True).count(),
                "upcoming_events": Event.objects.filter(is_active=True).count(),
                "total_suggestions": total_suggestions,
                "implemented_suggestions": implemented_suggestions,
            }
        )


class TransparencyStatsView(views.APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

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

        total = complaints.count()
        resolved = complaints.filter(status=ComplaintStatus.RESOLVED).count()
        all_suggestions = Suggestion.objects.all()
        total_suggestions = all_suggestions.count()
        implemented_suggestions = all_suggestions.filter(status=SuggestionStatus.IMPLEMENTED).count()
        now = timezone.now()
        open_suggestions = all_suggestions.exclude(status=SuggestionStatus.IMPLEMENTED)
        return Response(
            {
                "total_complaints": total,
                "resolved_complaints": resolved,
                "open_complaints": complaints.exclude(status=ComplaintStatus.RESOLVED).count(),
                "resolution_rate": round((resolved / total) * 100) if total else 0,
                "ministry_stats": ministry_stats,
                "total_suggestions": total_suggestions,
                "implemented_suggestions": implemented_suggestions,
                "pending_suggestions": open_suggestions.count(),
                "overdue_suggestions": open_suggestions.filter(due_at__lt=now).count(),
                "suggestion_review_rate": round((implemented_suggestions / total_suggestions) * 100)
                if total_suggestions
                else 0,
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

        serializer = AdminUserUpdateSerializer(data=request.data, partial=True, context={"user": user})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if "is_active" in data:
            is_active = data["is_active"]
            if user.pk == request.user.pk and not is_active:
                return Response({"detail": "You cannot deactivate your own account."}, status=status.HTTP_400_BAD_REQUEST)
            user.is_active = is_active

        if "role" in data:
            user.role = data["role"]
        if "ministry" in data:
            user.ministry = data["ministry"]
        if "first_name" in data:
            user.first_name = data["first_name"]
        if "last_name" in data:
            user.last_name = data["last_name"]
        if "email" in data:
            user.email = data["email"]

        user.save()
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

    def patch(self, request, pk: int):
        try:
            document = Document.objects.get(pk=pk, is_published=True)
        except Document.DoesNotExist:
            return Response({"detail": "Document not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = AdminDocumentUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(document, field, value)
        document.save()
        return Response(DocumentSerializer(document, context={"request": request}).data)

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


class AdminContactMessageDetailView(views.APIView):
    permission_classes = [*AUTHENTICATED, IsAdminRole]

    def patch(self, request, pk: int):
        try:
            message = ContactMessage.objects.get(pk=pk)
        except ContactMessage.DoesNotExist:
            return Response({"detail": "Message not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = AdminContactMessageUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message.is_read = serializer.validated_data["is_read"]
        message.save(update_fields=["is_read"])
        return Response(AdminContactMessageSerializer(message).data)


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


class AdminClubDetailView(views.APIView):
    permission_classes = [*AUTHENTICATED, IsAdminRole]

    def patch(self, request, pk: int):
        try:
            club = Club.objects.get(pk=pk)
        except Club.DoesNotExist:
            return Response({"detail": "Club not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = AdminClubUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(club, field, value)
        club.save()
        return Response(ClubSerializer(club, context={"request": request}).data)

    def delete(self, request, pk: int):
        try:
            club = Club.objects.get(pk=pk)
        except Club.DoesNotExist:
            return Response({"detail": "Club not found."}, status=status.HTTP_404_NOT_FOUND)
        club.is_active = False
        club.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)


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


class AdminEventDetailView(views.APIView):
    permission_classes = [*AUTHENTICATED, IsAdminRole]

    def patch(self, request, pk: int):
        try:
            event = Event.objects.get(pk=pk)
        except Event.DoesNotExist:
            return Response({"detail": "Event not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = AdminEventUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(event, field, value)
        event.save()
        return Response(EventSerializer(event, context={"request": request}).data)

    def delete(self, request, pk: int):
        try:
            event = Event.objects.get(pk=pk)
        except Event.DoesNotExist:
            return Response({"detail": "Event not found."}, status=status.HTTP_404_NOT_FOUND)
        event.is_active = False
        event.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminBackupView(views.APIView):
    permission_classes = [*AUTHENTICATED, IsAdminRole]

    def post(self, request):
        return Response(build_portal_backup())


class AdminSystemStatusView(views.APIView):
    permission_classes = [*AUTHENTICATED, IsAdminRole]

    def get(self, request):
        from django.conf import settings
        from django.db import connection

        db_ok = True
        try:
            connection.ensure_connection()
        except Exception:
            db_ok = False

        email_configured = bool(settings.EMAIL_HOST and settings.EMAIL_HOST_USER)
        if settings.EMAIL_BACKEND.endswith("console.EmailBackend"):
            email_configured = settings.DEBUG

        now = timezone.now()
        open_complaints = Complaint.objects.exclude(status=ComplaintStatus.RESOLVED)
        open_suggestions = Suggestion.objects.exclude(status=SuggestionStatus.IMPLEMENTED)

        return Response(
            {
                "api": "ok",
                "database": "connected" if db_ok else "error",
                "email_configured": email_configured,
                "sms_configured": bool(
                    getattr(settings, "SMS_ENABLED", False)
                    and getattr(settings, "SMS_API_KEY", "")
                    and getattr(settings, "SMS_USERNAME", "")
                ),
                "storage_configured": bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY),
                "registry_configured": registry_enabled(),
                "debug": settings.DEBUG,
                "ssl_enabled": not settings.DEBUG,
                "overdue_complaints": open_complaints.filter(due_at__lt=now).count(),
                "overdue_suggestions": open_suggestions.filter(due_at__lt=now).count(),
                "open_complaints": open_complaints.count(),
                "pending_suggestions": open_suggestions.count(),
                "cron_runs": [
                    {
                        "job_name": run.job_name,
                        "ran_at": run.ran_at.isoformat(),
                        "detail": run.detail,
                        "success": run.success,
                    }
                    for run in CronJobLog.objects.order_by("-ran_at")[:10]
                ],
            }
        )


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
