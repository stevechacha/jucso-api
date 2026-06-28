# Generated migration for Supabase storage paths

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="complaint",
            name="supporting_document_path",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="document",
            name="storage_path",
            field=models.CharField(blank=True, max_length=500),
        ),
    ]
