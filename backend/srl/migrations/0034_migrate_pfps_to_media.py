# Custom migration to fix an issue where the pfps were not being pushed to media.

import os

from django.conf import settings
from django.db import migrations


def migrate_pfp_urls_forward(apps, schema_editor):
    Players = apps.get_model("srl", "Players")
    pfp_dir = os.path.join(settings.MEDIA_ROOT, "pfp")

    if not os.path.isdir(pfp_dir):
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "UPDATE srl_players SET pfp = REPLACE(pfp, '/static/pfp/', '/media/pfp/')"
            " WHERE pfp LIKE '/static/pfp/%%'"
        )

    pfp_files = {
        os.path.splitext(f)[0]: f for f in os.listdir(pfp_dir) if f.endswith(".jpg")
    }

    players_missing_pfp = Players.objects.filter(
        id__in=pfp_files.keys(),
        pfp__isnull=True,
    )

    for player in players_missing_pfp:
        player.pfp = f"{settings.MEDIA_URL}pfp/{player.id}.jpg"

    Players.objects.bulk_update(players_missing_pfp, ["pfp"])


def migrate_pfp_urls_backward(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "UPDATE srl_players SET pfp = REPLACE(pfp, '/media/pfp/', '/static/pfp/')"
            " WHERE pfp LIKE '/media/pfp/%%'"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("srl", "0033_alter_awards_image_alter_runs_approver_and_more"),
    ]

    operations = [
        migrations.RunPython(
            migrate_pfp_urls_forward,
            migrate_pfp_urls_backward,
        ),
    ]
