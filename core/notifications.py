from django.conf import settings
from django.core.mail import send_mail

from core.models import Complaint, Suggestion
from core.sms import send_sms


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


def send_complaint_update_sms(complaint: Complaint) -> None:
    student = complaint.student
    if not student.phone_number:
        return
    message = (
        f"JUCSO {complaint.tracking_id}: status is now {complaint.status}. "
        f"Ministry: {complaint.ministry.name}."
    )
    if complaint.response:
        message = f"{message} Response: {complaint.response[:80]}"
    send_sms(student.phone_number, message)


def send_suggestion_update_email(suggestion: Suggestion) -> None:
    student = suggestion.student
    if not student.email:
        return

    frontend = settings.FRONTEND_URL.rstrip("/")
    subject = f"JUCSO suggestion {suggestion.pk:03d} — {suggestion.status}"
    lines = [
        f"Hello {student.display_name},",
        "",
        f'Your suggestion "{suggestion.title}" has been updated.',
        f"Status: {suggestion.status}",
    ]
    if suggestion.response:
        lines.extend(["", "Feedback from leadership:", suggestion.response])
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


def send_suggestion_update_sms(suggestion: Suggestion) -> None:
    student = suggestion.student
    if not student.phone_number:
        return
    message = f'JUCSO suggestion "{suggestion.title[:40]}": status is now {suggestion.status}.'
    if suggestion.response:
        message = f"{message} {suggestion.response[:60]}"
    send_sms(student.phone_number, message)


def notify_complaint_update(complaint: Complaint) -> None:
    send_complaint_update_email(complaint)
    send_complaint_update_sms(complaint)


def notify_suggestion_update(suggestion: Suggestion) -> None:
    send_suggestion_update_email(suggestion)
    send_suggestion_update_sms(suggestion)


def send_complaint_submitted_email(complaint: Complaint) -> None:
    student = complaint.student
    if not student.email:
        return

    frontend = settings.FRONTEND_URL.rstrip("/")
    subject = f"JUCSO complaint received — {complaint.tracking_id}"
    lines = [
        f"Hello {student.display_name},",
        "",
        "Your complaint has been submitted successfully.",
        f"Tracking ID: {complaint.tracking_id}",
        f"Category: {complaint.category}",
        f"Ministry: {complaint.ministry.name}",
        f"Status: {complaint.status}",
        "",
        f"Track progress anytime: {frontend}/track",
        f"Sign in for full details: {frontend}/dashboard",
        "",
        "— JUCSO Digital Portal",
    ]
    send_mail(
        subject,
        "\n".join(lines),
        settings.DEFAULT_FROM_EMAIL,
        [student.email],
        fail_silently=True,
    )


def send_complaint_submitted_sms(complaint: Complaint) -> None:
    student = complaint.student
    if not student.phone_number:
        return
    send_sms(
        student.phone_number,
        f"JUCSO complaint {complaint.tracking_id} received. Routed to {complaint.ministry.name}. Track at jucso portal.",
    )


def notify_complaint_submitted(complaint: Complaint) -> None:
    send_complaint_submitted_email(complaint)
    send_complaint_submitted_sms(complaint)
