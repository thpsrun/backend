# Generated manually on 2026-03-16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("srl", "0022_player_auth_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="players",
            name="is_claimed",
            field=models.BooleanField(
                default=False,
                help_text="True when player has signed up and linked their account.",
                verbose_name="Account Claimed",
            ),
        ),
        migrations.AlterField(
            model_name="players",
            name="sync_paused",
            field=models.BooleanField(
                default=False,
                help_text="When checked, SRC sync will skip this player.",
                verbose_name="Sync Paused",
            ),
        ),
    ]
