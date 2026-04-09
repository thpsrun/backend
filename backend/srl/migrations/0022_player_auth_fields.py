# Generated manually on 2026-03-15

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("srl", "0021_remove_runs_idx_runs_game_cat_sub_level_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="players",
            name="user",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="player",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="players",
            name="is_claimed",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="players",
            name="sync_paused",
            field=models.BooleanField(default=False),
        ),
    ]
