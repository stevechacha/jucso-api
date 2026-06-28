from django.conf import settings
from django.core.mail import send_mail

from core.models import Complaint


def send_complaint_update_email(complaint: Complaint) -> None:
    student = complaint.student
    if not student.email:
        return

    frontend = settings.FRONTEND_URL.rstrip("/")
    subject = f"JUCSO complaint {complaint.tracking_id} — {complaint.status}"
    lines = [
        f"Hello {student.display_name},",
        "",
        f"Your complaint ({complaint.tracking_id}) has been updated.",
        f"Category: {complaint.category}",
        f"Ministry: {complaint.ministry.name}",
        f"Status: {complaint.status}",
    ]
    if complaint.response:
        lines.extend(["", "Response from leadership:", complaint.response])
    lines.extend(
        [
            "",
            f"Sign in to view details: {frontend}/dashboard",
            "",
            "— JUCSO Digital Portal",
        ]
    )

    send_mail(
        subject,
        "\n".join(lines),
        settings.DEFAULT_FROM_EMAIL,
        [student.email],
        fail_silently=True,
    )
