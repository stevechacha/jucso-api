from django.core.management.base import BaseCommand
from django.utils import timezone

from core.cron_log import log_cron_run
from core.models import Complaint, ComplaintStatus
from core.notifications import notify_overdue_complaint


class Command(BaseCommand):
    help = "Notify ministers and leadership about complaints past their SLA due date."

    def handle(self, *args, **options):
        now = timezone.now()
        overdue = Complaint.objects.filter(
            due_at__lt=now,
            sla_notified_at__isnull=True,
        ).exclude(status=ComplaintStatus.RESOLVED).select_related("student", "ministry")

        count = 0
        for complaint in overdue:
            notify_overdue_complaint(complaint)
            complaint.sla_notified_at = now
            complaint.save(update_fields=["sla_notified_at"])
            count += 1

        detail = f"Sent {count} overdue complaint alert(s)."
        log_cron_run(job_name="notify_overdue_complaints", detail=detail, success=True)
        self.stdout.write(self.style.SUCCESS(detail))
