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

    def test_password_reset_request_returns_generic_message(self):
        with self.settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            response = self.client.post(
                "/api/auth/password-reset/",
                {"email": "student@jucso.ac.tz"},
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("detail", response.json())

    def test_password_reset_confirm_updates_password(self):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        uid = urlsafe_base64_encode(force_bytes(self.student.pk))
        token = default_token_generator.make_token(self.student)

        response = self.client.post(
            "/api/auth/password-reset/confirm/",
            {"uid": uid, "token": token, "password": "NewSecurePass456!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password("NewSecurePass456!"))

    def test_admin_created_staff_must_change_password(self):
        admin = User.objects.create_user(
            username="admin-001",
            reg_number="ADMIN/001",
            email="admin@jucso.ac.tz",
            password="SecurePass123!",
            first_name="System",
            last_name="Admin",
            role="admin",
        )
        self.client.force_authenticate(user=admin)
        response = self.client.post(
            "/api/admin/staff/",
            {
                "reg_number": "MIN/SPORT/002",
                "first_name": "New",
                "last_name": "Minister",
                "email": "new.minister@jucso.ac.tz",
                "password": "JUCSO-TempPass1!",
                "role": "minister",
                "ministry": "Sports",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = User.objects.get(reg_number="MIN/SPORT/002")
        self.assertTrue(created.must_change_password)

    def test_staff_with_temp_password_blocked_until_changed(self):
        temp_user = User.objects.create_user(
            username="min-sport-002",
            reg_number="MIN/SPORT/003",
            email="temp.minister@jucso.ac.tz",
            password="JUCSO-TempPass1!",
            first_name="Temp",
            last_name="Minister",
            role="minister",
            ministry="Sports",
            must_change_password=True,
        )
        self.client.force_authenticate(user=temp_user)
        blocked = self.client.get("/api/complaints/")
        self.assertEqual(blocked.status_code, status.HTTP_403_FORBIDDEN)

        allowed = self.client.get("/api/auth/me/")
        self.assertEqual(allowed.status_code, status.HTTP_200_OK)
        self.assertTrue(allowed.json()["must_change_password"])

    def test_change_password_clears_must_change_flag(self):
        temp_user = User.objects.create_user(
            username="exec-vice-002",
            reg_number="EXEC/VICE/002",
            email="temp.exec@jucso.ac.tz",
            password="JUCSO-TempPass1!",
            first_name="Temp",
            last_name="Executive",
            role="executive",
            must_change_password=True,
        )
        self.client.force_authenticate(user=temp_user)
        response = self.client.post(
            "/api/auth/change-password/",
            {"current_password": "JUCSO-TempPass1!", "new_password": "MyNewSecurePass789!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertFalse(body["user"]["must_change_password"])
        temp_user.refresh_from_db()
        self.assertFalse(temp_user.must_change_password)
        self.assertTrue(temp_user.check_password("MyNewSecurePass789!"))

        self.client.force_authenticate(user=temp_user)
        complaints = self.client.get("/api/complaints/")
        self.assertEqual(complaints.status_code, status.HTTP_200_OK)

    def test_admin_can_publish_news(self):
        admin = User.objects.create_user(
            username="admin-news",
            reg_number="ADMIN/NEWS",
            email="admin.news@jucso.ac.tz",
            password="SecurePass123!",
            first_name="News",
            last_name="Admin",
            role="admin",
        )
        self.client.force_authenticate(user=admin)
        response = self.client.post(
            "/api/admin/news/",
            {
                "title": "Exam Timetable Released",
                "excerpt": "Semester 1 exam timetable is now available on the portal.",
                "tag": "Notice",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()["title"], "Exam Timetable Released")
