from datetime import date

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import (
    CATEGORY_TO_MINISTRY,
    Club,
    Complaint,
    ComplaintCategory,
    Document,
    Event,
    Ministry,
    NewsItem,
    NewsTag,
    Suggestion,
    SuggestionStatus,
    UserRole,
)

User = get_user_model()

DEMO_PASSWORD = "demo123"

USERS = [
    ("JUC/2024/001", "Amara", "Osei", "student", "", "amara.osei@jucso.ac.tz"),
    ("JUC/2024/002", "Leilani", "Mwamba", "student", "", "leilani.mwamba@jucso.ac.tz"),
    ("MIN/ACAD/001", "Amani", "Kiprotich", "minister", "Academics", "amani.kiprotich@jucso.ac.tz"),
    ("MIN/FIN/001", "Baraka", "Omondi", "minister", "Finance", "baraka.omondi@jucso.ac.tz"),
    ("MIN/HLTH/001", "Zawadi", "Moshi", "minister", "Health & Welfare", "zawadi.moshi@jucso.ac.tz"),
    ("MIN/SOC/001", "Farida", "Juma", "minister", "Social Affairs", "farida.juma@jucso.ac.tz"),
    ("MIN/ACC/001", "Tumelo", "Banda", "minister", "Accommodation", "tumelo.banda@jucso.ac.tz"),
    ("MIN/SPT/001", "Kioni", "Njoroge", "minister", "Sports & Recreation", "kioni.njoroge@jucso.ac.tz"),
    ("EXEC/PRES/001", "Neema", "Salim", "executive", "", "neema.salim@jucso.ac.tz"),
    ("ADMIN/001", "System", "Administrator", "admin", "", "admin@jucso.ac.tz"),
]


class Command(BaseCommand):
    help = "Seed ministries, demo users, and sample portal data"

    @transaction.atomic
    def handle(self, *args, **options):
        ministries = {}
        for ministry_name in set(CATEGORY_TO_MINISTRY.values()):
            ministry, _ = Ministry.objects.get_or_create(
                name=ministry_name,
                defaults={"slug": ministry_name.lower().replace(" ", "-").replace("&", "and")},
            )
            ministries[ministry_name] = ministry

        for reg, first, last, role, ministry, email in USERS:
            username = reg.lower().replace("/", "-")
            user, created = User.objects.get_or_create(
                reg_number=reg,
                defaults={
                    "username": username,
                    "first_name": first,
                    "last_name": last,
                    "email": email,
                    "role": role,
                    "ministry": ministry,
                    "phone_number": "+255700000000",
                },
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save()
                self.stdout.write(f"Created user {reg}")
            else:
                user.set_password(DEMO_PASSWORD)
                user.save(update_fields=["password"])

        students = {u.reg_number: u for u in User.objects.filter(role=UserRole.STUDENT)}

        complaints_data = [
            ("JUC-001", "JUC/2024/001", ComplaintCategory.ACADEMIC, "Library books for ECO 301 are insufficient — only 3 copies for 200+ students.", "Pending", True, ""),
            ("JUC-002", "JUC/2024/002", ComplaintCategory.FINANCIAL, "HESLB loan disbursement delayed by 3 weeks with no official communication.", "In Progress", False, "We have escalated this to HESLB. Expect resolution by June 30."),
            ("JUC-003", "JUC/2024/001", ComplaintCategory.ACCOMMODATION, "Room 14B has a broken ceiling fan and leaking roof — reported twice with no action.", "Resolved", False, "Maintenance team repaired both issues on June 18. Please confirm."),
            ("JUC-004", "JUC/2024/002", ComplaintCategory.HEALTH, "College dispensary is unstaffed during afternoon hours (1–3 PM daily).", "Pending", True, ""),
            ("JUC-005", "JUC/2024/001", ComplaintCategory.ACADEMIC, "Computer lab PCs in Block C are running outdated software — cannot run required coursework.", "In Progress", False, ""),
            ("JUC-006", "JUC/2024/002", ComplaintCategory.SOCIAL, "Student common room lights broken for two months — reported to housing but no action.", "Pending", False, ""),
        ]

        for tracking_id, student_reg, category, description, status, urgent, response in complaints_data:
            ministry_name = CATEGORY_TO_MINISTRY[category]
            Complaint.objects.update_or_create(
                tracking_id=tracking_id,
                defaults={
                    "student": students[student_reg],
                    "category": category,
                    "description": description,
                    "ministry": ministries[ministry_name],
                    "status": status,
                    "urgent": urgent,
                    "response": response,
                },
            )

        suggestions_data = [
            ("JUC/2024/001", "Extended Library Hours", "Library should stay open until midnight during exam periods.", SuggestionStatus.UNDER_REVIEW),
            ("JUC/2024/002", "Mental Health Counselor", "Hire a full-time student counselor — many students struggle silently.", SuggestionStatus.RECEIVED),
            ("JUC/2024/001", "Online Lecture Recordings", "Record and upload all lectures to the student portal for revision.", SuggestionStatus.IMPLEMENTED),
        ]
        for student_reg, title, description, status in suggestions_data:
            Suggestion.objects.get_or_create(
                student=students[student_reg],
                title=title,
                defaults={"description": description, "status": status},
            )

        clubs_data = [
            ("Debate & Public Speaking Society", "Weekly debates, public speaking coaching, and national competition participation.", 47, "Dr. Kamau", "Academic"),
            ("Environmental Action Club", "Tree planting, campus clean-ups, and sustainability advocacy.", 63, "Prof. Wanjiku", "Community"),
            ("Tech & Innovation Hub", "Coding bootcamps, hackathons, and entrepreneurship workshops.", 88, "Mr. Ochieng", "Academic"),
            ("Dance & Performing Arts", "Traditional and contemporary dance, theatre, and cultural showcases.", 35, "Ms. Abebe", "Arts"),
            ("Chess & Strategy Club", "Weekly tournaments, coaching sessions, and inter-university competitions.", 22, "Mr. Msomi", "Recreation"),
            ("Community Service Corps", "Off-campus volunteer programs, hospital visits, and primary school tutoring.", 54, "Dr. Ngugi", "Community"),
        ]
        for name, description, members, leader, category in clubs_data:
            Club.objects.update_or_create(
                name=name,
                defaults={
                    "description": description,
                    "members_count": members,
                    "leader": leader,
                    "category": category,
                    "is_active": True,
                },
            )

        events_data = [
            ("JUCSO Annual Freshers' Welcome", "Welcome ceremony for 2026 intake. Musical performances, introductions, and refreshments.", "Main Auditorium", date(2026, 7, 8), 400, 287),
            ("Career Fair 2026", "50+ companies on campus. Bring your CV and dress professionally.", "Student Centre", date(2026, 7, 15), 300, 189),
            ("Inter-University Debate Championship", "JUCSO Debate Society hosts five universities. Open viewing for all students.", "Conference Hall A", date(2026, 7, 20), 200, 142),
            ("Health Awareness Week Launch", "Free medical screenings, mental health workshops, and nutrition talks.", "Campus Grounds", date(2026, 8, 1), 500, 93),
        ]
        for title, description, location, event_date, capacity, registered in events_data:
            Event.objects.update_or_create(
                title=title,
                defaults={
                    "description": description,
                    "location": location,
                    "event_date": event_date,
                    "capacity": capacity,
                    "registered_count": registered,
                    "is_active": True,
                },
            )

        news_data = [
            ("Digital Portal Launch: What Every Student Needs to Know", "The JUCSO Digital Student Government Management System officially launches this month. All students must register using their reg number.", date(2026, 6, 28), NewsTag.ANNOUNCEMENT),
            ("Freshers' Welcome 2026 — Registration Now Open", "If you joined Jordan University College in 2026, register for the official welcome ceremony by July 5.", date(2026, 6, 25), NewsTag.EVENTS),
            ("Tech & Innovation Hub Recruiting New Members", "The Tech Hub is accepting applications for Semester 1. No prior coding experience required — just curiosity.", date(2026, 6, 22), NewsTag.CLUBS),
            ("HESLB Loan Disbursements: Official Timeline", "The Ministry of Finance has confirmed HESLB disbursements will be processed in two batches: June 30 and July 7.", date(2026, 6, 20), NewsTag.NOTICE),
            ("Career Fair 2026 — 50 Companies Confirmed", "This year's career fair features firms from finance, tech, engineering, and health. Dress code is smart casual.", date(2026, 6, 18), NewsTag.EVENTS),
            ("Library Hours Extended for Exam Season", "Following student feedback, the library will operate 7AM–11PM from July 1 through August 15.", date(2026, 6, 15), NewsTag.ANNOUNCEMENT),
        ]
        for title, excerpt, published_at, tag in news_data:
            NewsItem.objects.update_or_create(
                title=title,
                defaults={"excerpt": excerpt, "published_at": published_at, "tag": tag, "is_published": True},
            )

        docs_data = [
            ("JUCSO Constitution 2026", "1.2 MB", date(2026, 1, 1)),
            ("Election Bylaws & Procedures", "856 KB", date(2026, 2, 1)),
            ("Student Rights & Responsibilities Charter", "643 KB", date(2026, 3, 1)),
            ("Meeting Minutes — June 2026", "312 KB", date(2026, 6, 1)),
            ("Ministry Performance Report Q1 2026", "2.1 MB", date(2026, 4, 1)),
        ]
        for name, size, published_at in docs_data:
            Document.objects.update_or_create(
                name=name,
                defaults={"file_size": size, "file_type": "PDF", "published_at": published_at, "is_published": True},
            )

        self.stdout.write(self.style.SUCCESS("JUCSO seed data loaded. Demo password: demo123"))
