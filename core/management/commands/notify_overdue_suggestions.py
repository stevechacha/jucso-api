from django.core.management.base import BaseCommand
from django.utils import timezone

from core.cron_log import log_cron_run
from core.models import Suggestion, SuggestionStatus
from core.notifications import notify_overdue_suggestion


class Command(BaseCommand):
    help = "Notify leadership about suggestions past their review SLA due date."

    def handle(self, *args, **options):
        now = timezone.now()
        overdue = Suggestion.objects.filter(
            due_at__lt=now,
            sla_notified_at__isnull=True,
        ).exclude(status=SuggestionStatus.IMPLEMENTED).select_related("student")

        count = 0
        for suggestion in overdue:
            notify_overdue_suggestion(suggestion)
            suggestion.sla_notified_at = now
            suggestion.save(update_fields=["sla_notified_at"])
            count += 1

        detail = f"Sent {count} overdue suggestion alert(s)."
        log_cron_run(job_name="notify_overdue_suggestions", detail=detail, success=True)
        self.stdout.write(self.style.SUCCESS(detail))
