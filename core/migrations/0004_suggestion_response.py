from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_user_must_change_password"),
    ]

    operations = [
        migrations.AddField(
            model_name="suggestion",
            name="response",
            field=models.TextField(blank=True),
        ),
    ]
