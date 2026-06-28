import django.db.models.deletion
from datetime import timedelta

from django.conf import settings
from django.db import migrations, models


def set_suggestion_due_dates(apps, schema_editor):
    Suggestion = apps.get_model("core", "Suggestion")
    sla_days = getattr(settings, "SUGGESTION_SLA_DAYS", 7)
    for suggestion in Suggestion.objects.filter(due_at__isnull=True):
        suggestion.due_at = suggestion.created_at + timedelta(days=sla_days)
        suggestion.save(update_fields=["due_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_phase2_features"),
    ]

    operations = [
        migrations.AddField(
            model_name="suggestion",
            name="due_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="suggestion",
            name="sla_notified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="suggestion",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.CreateModel(
            name="CronJobLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("job_name", models.CharField(max_length=100)),
                ("ran_at", models.DateTimeField(auto_now_add=True)),
                ("detail", models.TextField(blank=True)),
                ("success", models.BooleanField(default=True)),
            ],
            options={
                "ordering": ["-ran_at"],
            },
        ),
        migrations.RunPython(set_suggestion_due_dates, migrations.RunPython.noop),
    ]
