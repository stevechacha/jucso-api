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


def _admin_notification_emails() -> list[str]:
    from django.contrib.auth import get_user_model

    User = get_user_model()
    configured = getattr(settings, "ADMIN_NOTIFICATION_EMAIL", "").strip()
    if configured:
        return [email.strip() for email in configured.split(",") if email.strip()]

    return list(
        User.objects.filter(role="admin", is_active=True)
        .exclude(email="")
        .values_list("email", flat=True)
    )


def notify_contact_message(message) -> None:
    recipients = _admin_notification_emails()
    if not recipients:
        return

    frontend = settings.FRONTEND_URL.rstrip("/")
    subject = f"New contact message — {message.subject or 'No subject'}"
    lines = [
        f"From: {message.name} <{message.email}>",
        f"Subject: {message.subject or 'No subject'}",
        "",
        message.message,
        "",
        f"View in admin inbox: {frontend}/dashboard",
        "",
        "— JUCSO Digital Portal",
    ]
    send_mail(
        subject,
        "\n".join(lines),
        settings.DEFAULT_FROM_EMAIL,
        recipients,
        fail_silently=True,
    )


def notify_overdue_complaint(complaint: Complaint) -> None:
    from django.contrib.auth import get_user_model

    User = get_user_model()
    recipients = set(_admin_notification_emails())

    ministers = User.objects.filter(
        role="minister",
        ministry=complaint.ministry.name,
        is_active=True,
    ).exclude(email="")
    for email in ministers.values_list("email", flat=True):
        recipients.add(email)

    executives = User.objects.filter(role="executive", is_active=True).exclude(email="")
    for email in executives.values_list("email", flat=True):
        recipients.add(email)

    if not recipients:
        return

    frontend = settings.FRONTEND_URL.rstrip("/")
    due = complaint.due_at.strftime("%b %d, %Y") if complaint.due_at else "N/A"
    subject = f"Overdue complaint {complaint.tracking_id} — action required"
    lines = [
        f"Complaint {complaint.tracking_id} has exceeded the {getattr(settings, 'COMPLAINT_SLA_DAYS', 7)}-day SLA.",
        "",
        f"Category: {complaint.category}",
        f"Ministry: {complaint.ministry.name}",
        f"Status: {complaint.status}",
        f"Due date: {due}",
        f"Student: {complaint.student.display_name} ({complaint.student.reg_number})",
        "",
        f"Review in portal: {frontend}/dashboard",
        "",
        "— JUCSO Digital Portal",
    ]
    send_mail(
        subject,
        "\n".join(lines),
        settings.DEFAULT_FROM_EMAIL,
        list(recipients),
        fail_silently=True,
    )


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
