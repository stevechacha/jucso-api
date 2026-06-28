from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from core.models import (
    Club,
    ClubMembership,
    Complaint,
    ComplaintCategory,
    ComplaintStatus,
    ContactMessage,
    Document,
    Event,
    EventRegistration,
    Ministry,
    NewsItem,
    NewsTag,
    Suggestion,
    SuggestionStatus,
    UserRole,
)

from core.storage import get_storage

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("reg_number", "name", "role", "ministry", "email", "phone_number", "must_change_password")
        read_only_fields = fields

    def get_name(self, obj: User) -> str:
        return obj.display_name


class ProfileUpdateSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150, trim_whitespace=True, required=False)
    last_name = serializers.CharField(max_length=150, trim_whitespace=True, required=False)
    email = serializers.EmailField(required=False)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True, trim_whitespace=True)

    def validate_email(self, value: str) -> str:
        email = value.strip().lower()
        user = self.context.get("user")
        if user and User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("This email is already in use.")
        return email

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Provide at least one field to update.")
        return attrs


class ComplaintTrackRequestSerializer(serializers.Serializer):
    tracking_id = serializers.CharField(max_length=20, trim_whitespace=True)
    reg_number = serializers.CharField(max_length=50, trim_whitespace=True)


class ComplaintTrackSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="tracking_id", read_only=True)
    ministry = serializers.CharField(source="ministry.name", read_only=True)
    date = serializers.SerializerMethodField()

    class Meta:
        model = Complaint
        fields = ("id", "category", "ministry", "status", "date", "response")

    def get_date(self, obj: Complaint) -> str:
        return obj.date_submitted.strftime("%b %d, %Y")


class LoginSerializer(serializers.Serializer):
    reg_number = serializers.CharField(max_length=50, trim_whitespace=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    portal = serializers.ChoiceField(choices=[("student", "Student"), ("staff", "Staff")])

    def validate_reg_number(self, value: str) -> str:
        return value.strip()


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_blank=True)
    reg_number = serializers.CharField(max_length=50, required=False, allow_blank=True, trim_whitespace=True)

    def validate(self, attrs):
        email = (attrs.get("email") or "").strip()
        reg_number = (attrs.get("reg_number") or "").strip()
        if not email and not reg_number:
            raise serializers.ValidationError("Provide your email or registration / PF number.")
        attrs["email"] = email
        attrs["reg_number"] = reg_number
        return attrs


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, min_length=8, trim_whitespace=False)

    def validate_password(self, value: str) -> str:
        validate_password(value)
        return value


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, min_length=8, trim_whitespace=False)

    def validate_new_password(self, value: str) -> str:
        user = self.context.get("user")
        validate_password(value, user)
        return value


class StudentRegisterSerializer(serializers.Serializer):
    reg_number = serializers.CharField(max_length=50, trim_whitespace=True)
    first_name = serializers.CharField(max_length=150, trim_whitespace=True)
    last_name = serializers.CharField(max_length=150, trim_whitespace=True)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8, trim_whitespace=False)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True, trim_whitespace=True)

    def validate_reg_number(self, value: str) -> str:
        reg = value.strip()
        if User.objects.filter(reg_number=reg).exists():
            raise serializers.ValidationError("This registration number is already registered.")
        return reg

    def validate_email(self, value: str) -> str:
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("This email is already in use.")
        return email

    def validate_password(self, value: str) -> str:
        validate_password(value)
        return value


class StaffCreateSerializer(serializers.Serializer):
    reg_number = serializers.CharField(max_length=50, trim_whitespace=True)
    first_name = serializers.CharField(max_length=150, trim_whitespace=True)
    last_name = serializers.CharField(max_length=150, trim_whitespace=True)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8, trim_whitespace=False)
    role = serializers.ChoiceField(choices=[(UserRole.MINISTER, "Minister"), (UserRole.EXECUTIVE, "Executive")])
    ministry = serializers.CharField(max_length=100, required=False, allow_blank=True, trim_whitespace=True)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True, trim_whitespace=True)

    def validate_reg_number(self, value: str) -> str:
        reg = value.strip()
        if User.objects.filter(reg_number=reg).exists():
            raise serializers.ValidationError("This PF number is already registered.")
        return reg

    def validate_email(self, value: str) -> str:
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("This email is already in use.")
        return email

    def validate_password(self, value: str) -> str:
        validate_password(value)
        return value

    def validate(self, attrs):
        role = attrs.get("role")
        ministry = (attrs.get("ministry") or "").strip()
        if role == UserRole.MINISTER and not ministry:
            raise serializers.ValidationError({"ministry": "Ministry is required for ministers."})
        if role == UserRole.EXECUTIVE:
            attrs["ministry"] = ""
        return attrs


class MinistrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Ministry
        fields = ("id", "name", "slug")


class ComplaintSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="tracking_id", read_only=True)
    student_name = serializers.CharField(source="student.display_name", read_only=True)
    student_reg = serializers.CharField(source="student.reg_number", read_only=True)
    ministry = serializers.CharField(source="ministry.name", read_only=True)
    date = serializers.SerializerMethodField()
    supporting_document_url = serializers.SerializerMethodField()

    class Meta:
        model = Complaint
        fields = (
            "id",
            "category",
            "description",
            "ministry",
            "status",
            "date",
            "student_name",
            "student_reg",
            "response",
            "urgent",
            "is_confidential",
            "supporting_document_url",
        )
        read_only_fields = fields

    def get_date(self, obj: Complaint) -> str:
        return obj.date_submitted.strftime("%b %d, %Y")

    def get_supporting_document_url(self, obj: Complaint) -> str | None:
        if obj.supporting_document_path:
            return get_storage().signed_url(obj.supporting_document_path)
        if obj.supporting_document:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.supporting_document.url)
            return obj.supporting_document.url
        return None


class ComplaintCreateSerializer(serializers.Serializer):
    category = serializers.CharField(max_length=100)
    description = serializers.CharField()
    urgent = serializers.BooleanField(required=False, default=False)
    supporting_document = serializers.FileField(required=False, allow_empty_file=False)

    def validate_category(self, value: str) -> str:
        valid = {choice.value for choice in ComplaintCategory}
        if value not in valid:
            raise serializers.ValidationError("Invalid complaint category.")
        return value


class ComplaintUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=ComplaintStatus.choices, required=False)
    response = serializers.CharField(required=False, allow_blank=True)
    ministry = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Provide at least one field to update.")
        ministry = (attrs.get("ministry") or "").strip()
        if ministry and not Ministry.objects.filter(name=ministry).exists():
            raise serializers.ValidationError({"ministry": "Unknown ministry."})
        if ministry:
            attrs["ministry"] = ministry
        return attrs


class SuggestionSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    student_name = serializers.CharField(source="student.display_name", read_only=True)
    date = serializers.SerializerMethodField()

    class Meta:
        model = Suggestion
        fields = ("id", "title", "description", "student_name", "date", "status", "response")

    def get_id(self, obj: Suggestion) -> str:
        return f"SUG-{obj.pk:03d}"

    def get_date(self, obj: Suggestion) -> str:
        return obj.created_at.strftime("%b %d, %Y")


class SuggestionUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Suggestion
        fields = ("status", "response")

    def validate_status(self, value: str) -> str:
        valid = {choice.value for choice in SuggestionStatus}
        if value not in valid:
            raise serializers.ValidationError("Invalid suggestion status.")
        return value


class SuggestionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Suggestion
        fields = ("title", "description")


class ClubSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    members = serializers.IntegerField(source="members_count")
    joined = serializers.SerializerMethodField()

    class Meta:
        model = Club
        fields = ("id", "name", "description", "members", "leader", "category", "joined")

    def get_id(self, obj: Club) -> str:
        return f"CLB-{obj.pk:03d}"

    def get_joined(self, obj: Club) -> bool:
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return ClubMembership.objects.filter(club=obj, student=request.user).exists()


class EventSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    date = serializers.SerializerMethodField()
    registered = serializers.IntegerField(source="registered_count")
    is_registered = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = (
            "id",
            "title",
            "date",
            "location",
            "capacity",
            "registered",
            "description",
            "is_registered",
        )

    def get_id(self, obj: Event) -> str:
        return f"EVT-{obj.pk:03d}"

    def get_date(self, obj: Event) -> str:
        return obj.event_date.strftime("%b %d, %Y")

    def get_is_registered(self, obj: Event) -> bool:
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return EventRegistration.objects.filter(event=obj, student=request.user).exists()


class NewsItemSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    date = serializers.SerializerMethodField()
    tag = serializers.CharField()

    class Meta:
        model = NewsItem
        fields = ("id", "title", "excerpt", "date", "tag")

    def get_id(self, obj: NewsItem) -> str:
        return f"N{obj.pk:02d}"

    def get_date(self, obj: NewsItem) -> str:
        return obj.published_at.strftime("%b %d, %Y")


class DocumentSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    type = serializers.CharField(source="file_type")
    size = serializers.CharField(source="file_size")
    date = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = ("id", "name", "size", "type", "date", "download_url")

    def get_id(self, obj: Document) -> str:
        return f"DOC-{obj.pk:03d}"

    def get_date(self, obj: Document) -> str:
        return obj.published_at.strftime("%b %Y")

    def get_download_url(self, obj: Document) -> str | None:
        if obj.storage_path:
            return get_storage().download_url(obj.storage_path, public=True)
        if obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class AdminDocumentCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=300)
    file = serializers.FileField()
    file_type = serializers.CharField(max_length=20, required=False, allow_blank=True)
    published_at = serializers.DateField(required=False)


class AdminNewsCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=300, trim_whitespace=True)
    excerpt = serializers.CharField(trim_whitespace=True)
    tag = serializers.ChoiceField(choices=NewsTag.choices)
    published_at = serializers.DateField(required=False)


class AdminNewsUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=300, trim_whitespace=True, required=False)
    excerpt = serializers.CharField(trim_whitespace=True, required=False)
    tag = serializers.ChoiceField(choices=NewsTag.choices, required=False)
    is_published = serializers.BooleanField(required=False)


class AdminClubCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, trim_whitespace=True)
    description = serializers.CharField(trim_whitespace=True)
    leader = serializers.CharField(max_length=100, trim_whitespace=True)
    category = serializers.CharField(max_length=50, trim_whitespace=True)


class AdminEventCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, trim_whitespace=True)
    description = serializers.CharField(trim_whitespace=True)
    location = serializers.CharField(max_length=200, trim_whitespace=True)
    event_date = serializers.DateField()
    capacity = serializers.IntegerField(min_value=1)


class AdminClubUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, trim_whitespace=True, required=False)
    description = serializers.CharField(trim_whitespace=True, required=False)
    leader = serializers.CharField(max_length=100, trim_whitespace=True, required=False)
    category = serializers.CharField(max_length=50, trim_whitespace=True, required=False)


class AdminEventUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, trim_whitespace=True, required=False)
    description = serializers.CharField(trim_whitespace=True, required=False)
    location = serializers.CharField(max_length=200, trim_whitespace=True, required=False)
    event_date = serializers.DateField(required=False)
    capacity = serializers.IntegerField(min_value=1, required=False)


class LeadershipMemberSerializer(serializers.Serializer):
    name = serializers.CharField()
    role = serializers.CharField()
    ministry = serializers.CharField(allow_blank=True)
    initials = serializers.CharField()


class AdminContactMessageSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    date = serializers.SerializerMethodField()

    class Meta:
        model = ContactMessage
        fields = ("id", "name", "email", "subject", "message", "date", "is_read")

    def get_id(self, obj: ContactMessage) -> str:
        return f"MSG-{obj.pk:04d}"

    def get_date(self, obj: ContactMessage) -> str:
        return obj.created_at.strftime("%b %d, %Y %H:%M")


class AdminContactMessageUpdateSerializer(serializers.Serializer):
    is_read = serializers.BooleanField()


class ContactMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactMessage
        fields = ("name", "email", "subject", "message")


class AdminUserSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("reg_number", "name", "role", "ministry", "email", "is_active")

    def get_name(self, obj: User) -> str:
        return obj.display_name


class AdminUserUpdateSerializer(serializers.Serializer):
    is_active = serializers.BooleanField()
