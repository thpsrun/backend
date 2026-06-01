from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0007_alter_apiactivitylog_options"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="apiactivitylog",
            index=models.Index(
                fields=["-created_at"],
                name="apiactivitylog_created_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="apiactivitylog",
            index=models.Index(
                fields=["target_app", "target_model", "-created_at"],
                name="apiactivitylog_target_idx",
            ),
        ),
    ]
