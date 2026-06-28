from django.contrib.auth import get_user_model
from rest_framework import serializers

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


class UserSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("reg_number", "name", "role", "ministry", "email", "phone_number")
        read_only_fields = fields

    def get_name(self, obj: User) -> str:
        return obj.display_name


from core.models import UserRole


class LoginSerializer(serializers.Serializer):
    reg_number = serializers.CharField()
    password = serializers.CharField(write_only=True)
    role = serializers.ChoiceField(choices=UserRole.choices)


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
        )
        read_only_fields = ("id", "ministry", "status", "date", "student_name", "student_reg", "response")

    def get_date(self, obj: Complaint) -> str:
        return obj.date_submitted.strftime("%b %d, %Y")


class ComplaintCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Complaint
        fields = ("category", "description", "urgent", "supporting_document")


class ComplaintUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Complaint
        fields = ("status", "response")


class SuggestionSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    student_name = serializers.CharField(source="student.display_name", read_only=True)
    date = serializers.SerializerMethodField()

    class Meta:
        model = Suggestion
        fields = ("id", "title", "description", "student_name", "date", "status")
        read_only_fields = ("id", "student_name", "date", "status")

    def get_id(self, obj: Suggestion) -> str:
        return f"SUG-{obj.pk:03d}"

    def get_date(self, obj: Suggestion) -> str:
        return obj.created_at.strftime("%b %d, %Y")


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
        if obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


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
