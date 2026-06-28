from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from core.models import Complaint, Ministry, Suggestion, SuggestionStatus

User = get_user_model()


class PriorityFeaturesTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.ministry = Ministry.objects.create(name="Academics", slug="academics")
        self.student = User.objects.create_user(
            username="student-priority",
            reg_number="JUC/2026/010",
            email="priority.student@jucso.ac.tz",
            password="SecurePass123!",
            first_name="Priority",
            last_name="Student",
            role="student",
        )
        self.minister = User.objects.create_user(
            username="minister-priority",
            reg_number="MIN/ACAD/010",
            email="priority.minister@jucso.ac.tz",
            password="SecurePass123!",
            first_name="Priority",
            last_name="Minister",
            role="minister",
            ministry="Academics",
        )
        self.admin = User.objects.create_user(
            username="admin-priority",
            reg_number="ADMIN/010",
            email="priority.admin@jucso.ac.tz",
            password="SecurePass123!",
            first_name="Priority",
            last_name="Admin",
            role="admin",
        )
        self.complaint = Complaint.objects.create(
            tracking_id="JUC-P010",
            student=self.student,
            category="Academic Issues",
            description="Need transcript update.",
            ministry=self.ministry,
        )
        self.suggestion = Suggestion.objects.create(
            student=self.student,
            title="Library hours",
            description="Extend library hours.",
            status=SuggestionStatus.RECEIVED,
        )

    @patch("core.views.notify_complaint_update")
    def test_complaint_update_triggers_email(self, mock_send):
        self.client.force_authenticate(user=self.minister)
        response = self.client.patch(
            f"/api/complaints/{self.complaint.tracking_id}/",
            {"status": "In Progress", "response": "We are working on it."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_send.assert_called_once()

    def test_minister_can_update_suggestion(self):
        self.client.force_authenticate(user=self.minister)
        response = self.client.patch(
            f"/api/suggestions/{self.suggestion.pk}/",
            {"status": "Under Review", "response": "Good idea."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.suggestion.refresh_from_db()
        self.assertEqual(self.suggestion.status, SuggestionStatus.UNDER_REVIEW)
        self.assertEqual(self.suggestion.response, "Good idea.")

    def test_admin_can_deactivate_user(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(
            f"/api/admin/users/{self.student.reg_number}/",
            {"is_active": False},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_active)

    def test_admin_cannot_deactivate_self(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(
            f"/api/admin/users/{self.admin.reg_number}/",
            {"is_active": False},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_complaint_update_sends_email_when_smtp_configured(self):
        self.client.force_authenticate(user=self.minister)
        with self.settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            response = self.client.patch(
                f"/api/complaints/{self.complaint.tracking_id}/",
                {"status": "Resolved", "response": "Done."},
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.student.email, mail.outbox[0].to)
