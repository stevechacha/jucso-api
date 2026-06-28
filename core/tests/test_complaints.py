from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from core.models import Ministry

User = get_user_model()


class ComplaintFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.student = User.objects.create_user(
            username="juc-2024-002",
            reg_number="JUC/2024/002",
            email="student2@jucso.ac.tz",
            password="SecurePass123!",
            first_name="Leilani",
            last_name="Mwamba",
            role="student",
            email_verified=True,
        )
        self.minister = User.objects.create_user(
            username="min-acad-002",
            reg_number="MIN/ACAD/002",
            email="minister2@jucso.ac.tz",
            password="SecurePass123!",
            first_name="Amani",
            last_name="Kiprotich",
            role="minister",
            ministry="Academics",
        )
        self.ministry, _ = Ministry.objects.get_or_create(
            name="Academics",
            defaults={"slug": "academics"},
        )

    def test_student_can_create_complaint(self):
        self.client.force_authenticate(user=self.student)
        response = self.client.post(
            "/api/complaints/",
            {
                "category": "Academic Issues",
                "description": "Library hours are too short during exams.",
                "urgent": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = response.json()
        self.assertTrue(body["id"].startswith("JUC-"))
        self.assertEqual(body["status"], "Pending")

    def test_minister_cannot_create_complaint(self):
        self.client.force_authenticate(user=self.minister)
        response = self.client.post(
            "/api/complaints/",
            {
                "category": "Academic Issues",
                "description": "Should not be allowed.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_minister_sees_ministry_complaints_only(self):
        self.client.force_authenticate(user=self.student)
        self.client.post(
            "/api/complaints/",
            {"category": "Academic Issues", "description": "Academic issue"},
            format="json",
        )

        self.client.force_authenticate(user=self.minister)
        response = self.client.get("/api/complaints/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.json()["results"] if "results" in response.json() else response.json()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["ministry"], "Academics")
