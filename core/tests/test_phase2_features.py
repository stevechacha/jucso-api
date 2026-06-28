from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient

from core.models import Complaint, ComplaintActivity, ComplaintStatus, Ministry, UserRole
from core.services import create_complaint

User = get_user_model()


class Phase2FeaturesTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.student = User.objects.create_user(
            username="juc-2026-050",
            reg_number="JUC/2026/050",
            email="student50@jucso.ac.tz",
            password="StudentPass123!",
            first_name="Phase",
            last_name="Two",
            role=UserRole.STUDENT,
            email_verified=False,
        )
        self.minister = User.objects.create_user(
            username="min-acad-050",
            reg_number="MIN/ACAD/050",
            email="minister50@jucso.ac.tz",
            password="MinisterPass123!",
            role=UserRole.MINISTER,
            ministry="Academics",
            email_verified=True,
        )
        self.admin = User.objects.create_user(
            username="admin-050",
            reg_number="ADM/050",
            email="admin50@jucso.ac.tz",
            password="AdminPass123!",
            role=UserRole.ADMIN,
            email_verified=True,
        )
        Ministry.objects.get_or_create(name="Academics", defaults={"slug": "academics"})

    def test_complaint_requires_verified_email(self):
        self.client.force_authenticate(user=self.student)
        response = self.client.post(
            "/api/complaints/",
            {"category": "Academic Issues", "description": "Late exam results"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

        self.student.email_verified = True
        self.student.save()
        response = self.client.post(
            "/api/complaints/",
            {"category": "Academic Issues", "description": "Late exam results"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn("due_at", response.data)
        self.assertFalse(response.data["is_overdue"])
        complaint = Complaint.objects.get(tracking_id=response.data["id"])
        self.assertIsNotNone(complaint.due_at)
        self.assertEqual(complaint.activities.count(), 1)
        self.assertEqual(complaint.activities.first().action, "Submitted")

    def test_status_change_logs_activity(self):
        self.student.email_verified = True
        self.student.save()
        complaint = create_complaint(
            student=self.student,
            category="Academic Issues",
            description="Test issue",
        )
        self.client.force_authenticate(user=self.minister)
        response = self.client.patch(
            f"/api/complaints/{complaint.tracking_id}/",
            {"status": "In Progress", "response": "Looking into it"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(ComplaintActivity.objects.filter(complaint=complaint).count(), 2)
        self.assertTrue(any(a.action == "In Progress" for a in complaint.activities.all()))

    def test_contact_message_notifies_admin(self):
        mail.outbox.clear()
        response = self.client.post(
            "/api/contact/",
            {"name": "Jane", "email": "jane@example.com", "subject": "Hello", "message": "Need help"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("New contact message", mail.outbox[0].subject)

    @override_settings(ALLOWED_EMAIL_DOMAINS=["jucso.ac.tz"])
    def test_registration_requires_college_email(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "reg_number": "JUC/2026/099",
                "first_name": "Test",
                "last_name": "Student",
                "email": "bad@gmail.com",
                "password": "StudentPass123!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_public_stats_include_suggestions(self):
        response = self.client.get("/api/stats/public/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("total_suggestions", response.data)
        self.assertIn("implemented_suggestions", response.data)

    def test_minister_workload_view(self):
        self.student.email_verified = True
        self.student.save()
        create_complaint(student=self.student, category="Academic Issues", description="Open case")
        self.client.force_authenticate(user=self.minister)
        response = self.client.get("/api/stats/minister-workload/")
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.data["open_count"], 1)
        self.assertIn("resolved_this_week", response.data)

    def test_admin_can_edit_staff_role_and_ministry(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(
            f"/api/admin/users/{self.minister.reg_number}/",
            {"role": "executive", "ministry": ""},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.minister.refresh_from_db()
        self.assertEqual(self.minister.role, UserRole.EXECUTIVE)
        self.assertEqual(self.minister.ministry, "")

    def test_track_complaint_includes_activity(self):
        self.student.email_verified = True
        self.student.save()
        complaint = create_complaint(
            student=self.student,
            category="Academic Issues",
            description="Track me",
        )
        response = self.client.post(
            "/api/complaints/track/",
            {"tracking_id": complaint.tracking_id, "reg_number": self.student.reg_number},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("activity", response.data)
        self.assertGreaterEqual(len(response.data["activity"]), 1)

    def test_overdue_complaint_flag(self):
        self.student.email_verified = True
        self.student.save()
        complaint = create_complaint(
            student=self.student,
            category="Academic Issues",
            description="Overdue case",
        )
        complaint.due_at = timezone.now() - timedelta(days=1)
        complaint.save()
        self.client.force_authenticate(user=self.minister)
        response = self.client.get("/api/complaints/")
        self.assertEqual(response.status_code, 200)
        results = response.data["results"]
        overdue = next(c for c in results if c["id"] == complaint.tracking_id)
        self.assertTrue(overdue["is_overdue"])
