from django.db import migrations, models


def migrate_is_claimed_to_claim_status(apps, schema_editor):
    Players = apps.get_model("srl", "Players")
    Players.objects.filter(is_claimed=True, user__isnull=False).update(
        claim_status="claimed",
    )
    Players.objects.filter(is_claimed=True, user__isnull=True).update(
        claim_status="deleted",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("srl", "0023_player_auth_fields_metadata"),
    ]

    operations = [
        migrations.AddField(
            model_name="players",
            name="claim_status",
            field=models.CharField(
                choices=[
                    ("unclaimed", "Unclaimed"),
                    ("claimed", "Claimed"),
                    ("deleted", "Deleted"),
                ],
                default="unclaimed",
                help_text=(
                    "Tracks whether a player account is unclaimed, "
                    "actively claimed, or deleted."
                ),
                max_length=10,
                verbose_name="Claim Status",
            ),
        ),
        migrations.RunPython(
            migrate_is_claimed_to_claim_status,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
