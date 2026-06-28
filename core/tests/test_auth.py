from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

User = get_user_model()


class AuthFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.student = User.objects.create_user(
            username="juc-2024-001",
            reg_number="JUC/2024/001",
            email="student@jucso.ac.tz",
            password="SecurePass123!",
            first_name="Amara",
            last_name="Osei",
            role="student",
        )
        self.minister = User.objects.create_user(
            username="min-acad-001",
            reg_number="MIN/ACAD/001",
            email="minister@jucso.ac.tz",
            password="SecurePass123!",
            first_name="Amani",
            last_name="Kiprotich",
            role="minister",
            ministry="Academics",
        )

    def test_health_endpoint_is_public(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["status"], "ok")

    def test_student_login_returns_token_and_user(self):
        response = self.client.post(
            "/api/auth/login/",
            {"reg_number": "JUC/2024/001", "password": "SecurePass123!", "portal": "student"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertIn("access", body)
        self.assertEqual(body["user"]["role"], "student")

    def test_student_cannot_use_staff_portal(self):
        response = self.client.post(
            "/api/auth/login/",
            {"reg_number": "JUC/2024/001", "password": "SecurePass123!", "portal": "staff"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_minister_can_use_staff_portal(self):
        response = self.client.post(
            "/api/auth/login/",
            {"reg_number": "MIN/ACAD/001", "password": "SecurePass123!", "portal": "staff"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["user"]["role"], "minister")

    def test_register_creates_student_account(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "reg_number": "JUC/2025/100",
                "first_name": "New",
                "last_name": "Student",
                "email": "new.student@jucso.ac.tz",
                "password": "SecurePass123!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(reg_number="JUC/2025/100").exists())

    def test_me_requires_authentication(self):
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_returns_current_user(self):
        self.client.force_authenticate(user=self.student)
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["reg_number"], "JUC/2024/001")
