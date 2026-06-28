from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from core.models import Club, Complaint, Event, Ministry

User = get_user_model()


class AdditionalFeaturesTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.ministry = Ministry.objects.create(name="Academics", slug="academics")
        self.student = User.objects.create_user(
            username="student-additional",
            reg_number="JUC/2026/040",
            email="additional.student@jucso.ac.tz",
            password="SecurePass123!",
            first_name="Additional",
            last_name="Student",
            role="student",
            phone_number="0711223344",
        )
        self.admin = User.objects.create_user(
            username="admin-additional",
            reg_number="ADMIN/040",
            email="additional.admin@jucso.ac.tz",
            password="SecurePass123!",
            first_name="Additional",
            last_name="Admin",
            role="admin",
        )
        self.complaint = Complaint.objects.create(
            tracking_id="JUC-A040",
            student=self.student,
            category="Academic Issues",
            description="Library access issue.",
            ministry=self.ministry,
        )

    def test_public_can_track_complaint_with_reg_number(self):
        response = self.client.post(
            "/api/complaints/track/",
            {"tracking_id": "JUC-A040", "reg_number": "JUC/2026/040"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], "JUC-A040")
        self.assertNotIn("description", response.data)

    def test_track_complaint_rejects_wrong_reg_number(self):
        response = self.client.post(
            "/api/complaints/track/",
            {"tracking_id": "JUC-A040", "reg_number": "JUC/2026/999"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_student_can_update_profile(self):
        self.client.force_authenticate(user=self.student)
        response = self.client.patch(
            "/api/auth/me/",
            {"phone_number": "+255712345678", "first_name": "Updated"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.student.refresh_from_db()
        self.assertEqual(self.student.phone_number, "+255712345678")
        self.assertEqual(self.student.first_name, "Updated")

    def test_transparency_stats_are_public(self):
        response = self.client.get("/api/stats/transparency/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("resolution_rate", response.data)
        self.assertIn("ministry_stats", response.data)

    @patch("core.views.notify_complaint_submitted")
    def test_complaint_create_notifies_student(self, mock_notify):
        self.client.force_authenticate(user=self.student)
        response = self.client.post(
            "/api/complaints/",
            {"category": "Academic Issues", "description": "New issue."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_notify.assert_called_once()

    def test_admin_can_deactivate_club_and_event(self):
        club = Club.objects.create(
            name="Chess Club",
            description="Strategy games",
            leader="Sam",
            category="Academic",
            is_active=True,
        )
        event = Event.objects.create(
            title="Open Day",
            description="Welcome",
            location="Hall",
            event_date="2026-10-01",
            capacity=50,
            is_active=True,
        )
        self.client.force_authenticate(user=self.admin)
        club_response = self.client.delete(f"/api/admin/clubs/{club.pk}/")
        event_response = self.client.delete(f"/api/admin/events/{event.pk}/")
        self.assertEqual(club_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(event_response.status_code, status.HTTP_204_NO_CONTENT)
        club.refresh_from_db()
        event.refresh_from_db()
        self.assertFalse(club.is_active)
        self.assertFalse(event.is_active)
