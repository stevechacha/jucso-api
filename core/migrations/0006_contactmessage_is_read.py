from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_complaint_is_confidential"),
    ]

    operations = [
        migrations.AddField(
            model_name="contactmessage",
            name="is_read",
            field=models.BooleanField(default=False),
        ),
    ]
