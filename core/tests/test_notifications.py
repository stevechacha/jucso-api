from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from core.models import Ministry, Suggestion, SuggestionStatus
from core.sms import normalize_phone, send_sms

User = get_user_model()


class NotificationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.ministry = Ministry.objects.create(name="Academics", slug="academics")
        self.student = User.objects.create_user(
            username="student-notify",
            reg_number="JUC/2026/030",
            email="notify.student@jucso.ac.tz",
            password="SecurePass123!",
            first_name="Notify",
            last_name="Student",
            role="student",
            phone_number="0712345678",
            email_verified=True,
        )
        self.minister = User.objects.create_user(
            username="minister-notify",
            reg_number="MIN/ACAD/030",
            email="notify.minister@jucso.ac.tz",
            password="SecurePass123!",
            first_name="Notify",
            last_name="Minister",
            role="minister",
            ministry="Academics",
        )
        self.admin = User.objects.create_user(
            username="admin-notify",
            reg_number="ADMIN/030",
            email="notify.admin@jucso.ac.tz",
            password="SecurePass123!",
            first_name="Notify",
            last_name="Admin",
            role="admin",
        )
        self.suggestion = Suggestion.objects.create(
            student=self.student,
            title="Better cafeteria",
            description="Improve food options.",
            status=SuggestionStatus.RECEIVED,
        )

    @patch("core.views.notify_suggestion_update")
    def test_suggestion_update_triggers_notification(self, mock_notify):
        self.client.force_authenticate(user=self.minister)
        response = self.client.patch(
            f"/api/suggestions/{self.suggestion.pk}/",
            {"status": "Under Review", "response": "We will review this."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_notify.assert_called_once()

    def test_admin_can_view_system_status(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get("/api/admin/system-status/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["api"], "ok")
        self.assertIn("email_configured", response.data)
        self.assertIn("sms_configured", response.data)


class SmsUtilityTests(TestCase):
    def test_normalize_phone_adds_tanzania_prefix(self):
        self.assertEqual(normalize_phone("0712345678"), "+255712345678")

    @override_settings(
        SMS_ENABLED=True,
        SMS_PROVIDER="africas_talking",
        SMS_USERNAME="sandbox",
        SMS_API_KEY="test-key",
        SMS_SENDER_ID="JUCSO",
    )
    @patch("core.sms.urllib.request.urlopen")
    def test_send_sms_uses_africas_talking(self, mock_urlopen):
        mock_urlopen.return_value.__enter__.return_value.status = 200
        self.assertTrue(send_sms("0712345678", "Hello from JUCSO"))
        mock_urlopen.assert_called_once()
