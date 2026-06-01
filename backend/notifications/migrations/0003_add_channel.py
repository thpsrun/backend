from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0002_consolidate_export_pref"),
    ]

    operations = [
        migrations.AddField(
            model_name="notificationpreference",
            name="channel",
            field=models.CharField(
                max_length=20,
                choices=[("in_app", "In-app"), ("email", "Email")],
                default="in_app",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="notificationpreference",
            name="uniq_notif_pref_user_type",
        ),
        migrations.AddConstraint(
            model_name="notificationpreference",
            constraint=models.UniqueConstraint(
                fields=["user", "type", "channel"],
                name="uniq_notif_pref_user_type_channel",
            ),
        ),
    ]
