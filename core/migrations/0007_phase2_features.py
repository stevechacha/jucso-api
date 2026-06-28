import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone
from datetime import timedelta


def set_due_dates(apps, schema_editor):
    Complaint = apps.get_model("core", "Complaint")
    sla_days = getattr(settings, "COMPLAINT_SLA_DAYS", 7)
    for complaint in Complaint.objects.filter(due_at__isnull=True):
        complaint.due_at = complaint.date_submitted + timedelta(days=sla_days)
        complaint.save(update_fields=["due_at"])


def mark_existing_users_verified(apps, schema_editor):
    User = apps.get_model("core", "User")
    User.objects.filter(email_verified=False).update(email_verified=True)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_contactmessage_is_read"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="email_verified",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="complaint",
            name="due_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="complaint",
            name="sla_notified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="ComplaintActivity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(max_length=100)),
                ("detail", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="complaint_activities",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "complaint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="activities",
                        to="core.complaint",
                    ),
                ),
            ],
            options={
                "verbose_name_plural": "complaint activities",
                "ordering": ["created_at"],
            },
        ),
        migrations.RunPython(set_due_dates, migrations.RunPython.noop),
        migrations.RunPython(mark_existing_users_verified, migrations.RunPython.noop),
    ]
