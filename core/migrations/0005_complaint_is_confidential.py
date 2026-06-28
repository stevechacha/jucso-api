from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_suggestion_response"),
    ]

    operations = [
        migrations.AddField(
            model_name="complaint",
            name="is_confidential",
            field=models.BooleanField(default=False),
        ),
    ]
