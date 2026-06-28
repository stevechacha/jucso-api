from django.contrib.auth.models import AbstractUser
from django.db import models


class UserRole(models.TextChoices):
    STUDENT = "student", "Student"
    MINISTER = "minister", "Minister"
    EXECUTIVE = "executive", "Executive"
    ADMIN = "admin", "Admin"


class User(AbstractUser):
    reg_number = models.CharField(max_length=50, unique=True)
    role = models.CharField(max_length=20, choices=UserRole.choices, default=UserRole.STUDENT)
    ministry = models.CharField(max_length=100, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    must_change_password = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)

    REQUIRED_FIELDS = ["email", "reg_number"]

    class Meta:
        ordering = ["reg_number"]

    @property
    def display_name(self) -> str:
        return self.get_full_name() or self.username

    def __str__(self) -> str:
        return f"{self.reg_number} ({self.role})"


class Ministry(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "ministries"

    def __str__(self) -> str:
        return self.name


class ComplaintStatus(models.TextChoices):
    PENDING = "Pending", "Pending"
    IN_PROGRESS = "In Progress", "In Progress"
    RESOLVED = "Resolved", "Resolved"


class ComplaintCategory(models.TextChoices):
    ACADEMIC = "Academic Issues", "Academic Issues"
    FINANCIAL = "Financial / Loan Issues", "Financial / Loan Issues"
    HEALTH = "Health & Welfare", "Health & Welfare"
    ACCOMMODATION = "Accommodation", "Accommodation"
    SOCIAL = "Social Affairs", "Social Affairs"
    SPORTS = "Sports & Recreation", "Sports & Recreation"
    OTHER = "Other", "Other"


CATEGORY_TO_MINISTRY = {
    ComplaintCategory.ACADEMIC: "Academics",
    ComplaintCategory.FINANCIAL: "Finance",
    ComplaintCategory.HEALTH: "Health & Welfare",
    ComplaintCategory.ACCOMMODATION: "Accommodation",
    ComplaintCategory.SOCIAL: "Social Affairs",
    ComplaintCategory.SPORTS: "Sports & Recreation",
    ComplaintCategory.OTHER: "Academics",
}


class Complaint(models.Model):
    tracking_id = models.CharField(max_length=20, unique=True)
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="complaints")
    category = models.CharField(max_length=100, choices=ComplaintCategory.choices)
    description = models.TextField()
    ministry = models.ForeignKey(Ministry, on_delete=models.PROTECT, related_name="complaints")
    status = models.CharField(
        max_length=20,
        choices=ComplaintStatus.choices,
        default=ComplaintStatus.PENDING,
    )
    response = models.TextField(blank=True)
    urgent = models.BooleanField(default=False)
    is_confidential = models.BooleanField(default=False)
    supporting_document = models.FileField(upload_to="complaints/", blank=True, null=True)
    supporting_document_path = models.CharField(max_length=500, blank=True)
    date_submitted = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    due_at = models.DateTimeField(null=True, blank=True)
    sla_notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-date_submitted"]

    @property
    def is_overdue(self) -> bool:
        from django.utils import timezone

        if self.status == ComplaintStatus.RESOLVED or not self.due_at:
            return False
        return timezone.now() > self.due_at

    def __str__(self) -> str:
        return self.tracking_id


class ComplaintActivity(models.Model):
    complaint = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name="activities")
    action = models.CharField(max_length=100)
    detail = models.TextField(blank=True)
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="complaint_activities",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name_plural = "complaint activities"

    def __str__(self) -> str:
        return f"{self.complaint.tracking_id}: {self.action}"


class SuggestionStatus(models.TextChoices):
    RECEIVED = "Received", "Received"
    UNDER_REVIEW = "Under Review", "Under Review"
    IMPLEMENTED = "Implemented", "Implemented"


class Suggestion(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="suggestions")
    title = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=SuggestionStatus.choices,
        default=SuggestionStatus.RECEIVED,
    )
    response = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    due_at = models.DateTimeField(null=True, blank=True)
    sla_notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_overdue(self) -> bool:
        from django.utils import timezone

        if self.status == SuggestionStatus.IMPLEMENTED or not self.due_at:
            return False
        return timezone.now() > self.due_at

    def __str__(self) -> str:
        return self.title


class CronJobLog(models.Model):
    job_name = models.CharField(max_length=100)
    ran_at = models.DateTimeField(auto_now_add=True)
    detail = models.TextField(blank=True)
    success = models.BooleanField(default=True)

    class Meta:
        ordering = ["-ran_at"]

    def __str__(self) -> str:
        return f"{self.job_name} @ {self.ran_at:%Y-%m-%d %H:%M}"


class Club(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField()
    leader = models.CharField(max_length=100)
    category = models.CharField(max_length=50)
    members_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ClubMembership(models.Model):
    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name="memberships")
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="club_memberships")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("club", "student")

    def __str__(self) -> str:
        return f"{self.student.reg_number} → {self.club.name}"


class Event(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    location = models.CharField(max_length=200)
    event_date = models.DateField()
    capacity = models.PositiveIntegerField()
    registered_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["event_date"]

    def __str__(self) -> str:
        return self.title

    @property
    def is_full(self) -> bool:
        return self.registered_count >= self.capacity


class EventRegistration(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="registrations")
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="event_registrations")
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("event", "student")

    def __str__(self) -> str:
        return f"{self.student.reg_number} → {self.event.title}"


class NewsTag(models.TextChoices):
    ANNOUNCEMENT = "Announcement", "Announcement"
    EVENTS = "Events", "Events"
    CLUBS = "Clubs", "Clubs"
    NOTICE = "Notice", "Notice"


class NewsItem(models.Model):
    title = models.CharField(max_length=300)
    excerpt = models.TextField()
    tag = models.CharField(max_length=20, choices=NewsTag.choices)
    published_at = models.DateField()
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["-published_at"]

    def __str__(self) -> str:
        return self.title


class Document(models.Model):
    name = models.CharField(max_length=300)
    file = models.FileField(upload_to="documents/", blank=True, null=True)
    storage_path = models.CharField(max_length=500, blank=True)
    file_type = models.CharField(max_length=20, default="PDF")
    file_size = models.CharField(max_length=20, blank=True)
    published_at = models.DateField()
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["-published_at"]

    def __str__(self) -> str:
        return self.name


class ContactMessage(models.Model):
    name = models.CharField(max_length=200)
    email = models.EmailField()
    subject = models.CharField(max_length=300, blank=True)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name}: {self.subject or 'No subject'}"
