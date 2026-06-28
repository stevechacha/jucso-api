from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from core.models import (
    Club,
    Complaint,
    ComplaintCategory,
    ComplaintStatus,
    ContactMessage,
    Document,
    Event,
    Ministry,
    NewsItem,
)

User = get_user_model()


class RemainingFeaturesTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.academics = Ministry.objects.create(name="Academics", slug="academics")
        self.health = Ministry.objects.create(name="Health & Welfare", slug="health")
        self.student = User.objects.create_user(
            username="student-remaining",
            reg_number="JUC/2026/020",
            email="remaining.student@jucso.ac.tz",
            password="SecurePass123!",
            first_name="Remaining",
            last_name="Student",
            role="student",
        )
        self.minister = User.objects.create_user(
            username="minister-remaining",
            reg_number="MIN/ACAD/020",
            email="remaining.minister@jucso.ac.tz",
            password="SecurePass123!",
            first_name="Remaining",
            last_name="Minister",
            role="minister",
            ministry="Academics",
        )
        self.admin = User.objects.create_user(
            username="admin-remaining",
            reg_number="ADMIN/020",
            email="remaining.admin@jucso.ac.tz",
            password="SecurePass123!",
            first_name="Remaining",
            last_name="Admin",
            role="admin",
        )
        self.complaint = Complaint.objects.create(
            tracking_id="JUC-R020",
            student=self.student,
            category=ComplaintCategory.ACADEMIC,
            description="Need help.",
            ministry=self.academics,
        )

    def test_health_complaint_is_confidential_on_create(self):
        self.client.force_authenticate(user=self.student)
        response = self.client.post(
            "/api/complaints/",
            {
                "category": ComplaintCategory.HEALTH,
                "description": "Medical concern.",
                "urgent": False,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["is_confidential"])

    def test_minister_can_forward_complaint(self):
        self.client.force_authenticate(user=self.minister)
        response = self.client.patch(
            f"/api/complaints/{self.complaint.tracking_id}/",
            {"ministry": "Health & Welfare"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.ministry_id, self.health.pk)
        self.assertEqual(self.complaint.status, ComplaintStatus.PENDING)

    def test_admin_can_list_contact_messages(self):
        ContactMessage.objects.create(
            name="Jane Doe",
            email="jane@example.com",
            subject="Hello",
            message="Need info.",
        )
        self.client.force_authenticate(user=self.admin)
        response = self.client.get("/api/admin/contact-messages/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["subject"], "Hello")

    def test_admin_can_delete_news_and_document(self):
        news = NewsItem.objects.create(
            title="Test",
            excerpt="Summary",
            tag="Announcement",
            published_at="2026-06-01",
            is_published=True,
        )
        document = Document.objects.create(
            name="Handbook",
            file_type="PDF",
            file_size="1 MB",
            published_at="2026-06-01",
            is_published=True,
        )
        self.client.force_authenticate(user=self.admin)

        news_response = self.client.delete(f"/api/admin/news/{news.pk}/")
        self.assertEqual(news_response.status_code, status.HTTP_204_NO_CONTENT)
        news.refresh_from_db()
        self.assertFalse(news.is_published)

        doc_response = self.client.delete(f"/api/admin/documents/{document.pk}/")
        self.assertEqual(doc_response.status_code, status.HTTP_204_NO_CONTENT)
        document.refresh_from_db()
        self.assertFalse(document.is_published)

    def test_admin_can_create_club_and_event(self):
        self.client.force_authenticate(user=self.admin)

        club_response = self.client.post(
            "/api/admin/clubs/",
            {
                "name": "Debate Club",
                "description": "Weekly debates",
                "leader": "Alex Kim",
                "category": "Academic",
            },
            format="json",
        )
        self.assertEqual(club_response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Club.objects.filter(name="Debate Club").exists())

        event_response = self.client.post(
            "/api/admin/events/",
            {
                "title": "Orientation",
                "description": "Welcome event",
                "location": "Main Hall",
                "event_date": "2026-09-01",
                "capacity": 100,
            },
            format="json",
        )
        self.assertEqual(event_response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Event.objects.filter(title="Orientation").exists())

    def test_admin_can_update_news(self):
        news = NewsItem.objects.create(
            title="Old title",
            excerpt="Old summary",
            tag="Announcement",
            published_at="2026-06-01",
            is_published=True,
        )
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(
            f"/api/admin/news/{news.pk}/",
            {"title": "New title", "excerpt": "Updated summary"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        news.refresh_from_db()
        self.assertEqual(news.title, "New title")
        self.assertEqual(news.excerpt, "Updated summary")

    def test_admin_can_export_backup(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post("/api/admin/backup/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("exported_at", response.data)
        self.assertIn("complaints", response.data)
        self.assertIn("users", response.data)
        self.assertGreaterEqual(response.data["counts"]["users"], 3)

    def test_minister_can_list_ministries(self):
        self.client.force_authenticate(user=self.minister)
        response = self.client.get("/api/admin/ministries/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        names = {item["name"] for item in results}
        self.assertIn("Academics", names)
        self.assertIn("Health & Welfare", names)
