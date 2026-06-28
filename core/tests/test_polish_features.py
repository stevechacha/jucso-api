from datetime import timedelta

from django.core import mail
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient

from core.models import Suggestion, SuggestionStatus, User, UserRole

UserModel = User


class PolishFeaturesTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.student = User.objects.create_user(
            username="juc-polish-1",
            reg_number="JUC/2026/100",
            email="valid100@jucso.ac.tz",
            password="StudentPass123!",
            role=UserRole.STUDENT,
            email_verified=True,
        )
        self.admin = User.objects.create_user(
            username="admin-polish",
            reg_number="ADM/POL",
            email="admin-polish@jucso.ac.tz",
            password="AdminPass123!",
            role=UserRole.ADMIN,
            email_verified=True,
        )

    def test_suggestion_has_due_date_on_create(self):
        self.client.force_authenticate(user=self.student)
        response = self.client.post(
            "/api/suggestions/",
            {"title": "Library hours", "description": "Extend opening times"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn("due_at", response.data)
        self.assertFalse(response.data["is_overdue"])

    @override_settings(SUGGESTION_SLA_DAYS=7)
    def test_overdue_suggestion_flag(self):
        suggestion = Suggestion.objects.create(
            student=self.student,
            title="Old idea",
            description="Needs review",
            due_at=timezone.now() - timedelta(days=1),
        )
        self.client.force_authenticate(user=self.student)
        response = self.client.get("/api/suggestions/")
        self.assertEqual(response.status_code, 200)
        row = next(item for item in response.data["results"] if item["id"] == f"SUG-{suggestion.pk:03d}")
        self.assertTrue(row["is_overdue"])

    @override_settings(
        STUDENT_REGISTRY_CSV="core/tests/fixtures/student_registry.csv",
        ALLOWED_EMAIL_DOMAINS=["jucso.ac.tz"],
    )
    def test_registry_rejects_unknown_student(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "reg_number": "JUC/2099/999",
                "first_name": "Ghost",
                "last_name": "Student",
                "email": "ghost@jucso.ac.tz",
                "password": "StudentPass123!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    @override_settings(
        STUDENT_REGISTRY_CSV="core/tests/fixtures/student_registry.csv",
        ALLOWED_EMAIL_DOMAINS=["jucso.ac.tz"],
    )
    def test_registry_allows_listed_student(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "reg_number": "JUC/2026/101",
                "first_name": "Another",
                "last_name": "Student",
                "email": "valid101@jucso.ac.tz",
                "password": "StudentPass123!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)

    def test_system_status_includes_cron_and_registry_fields(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get("/api/admin/system-status/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("registry_configured", response.data)
        self.assertIn("cron_runs", response.data)
        self.assertIn("overdue_suggestions", response.data)

    def test_notify_overdue_suggestions_command(self):
        mail.outbox.clear()
        suggestion = Suggestion.objects.create(
            student=self.student,
            title="Late review",
            description="Still waiting",
            due_at=timezone.now() - timedelta(days=2),
        )
        from django.core.management import call_command

        call_command("notify_overdue_suggestions")
        suggestion.refresh_from_db()
        self.assertIsNotNone(suggestion.sla_notified_at)
        self.assertEqual(len(mail.outbox), 1)
