from django.db import migrations


def forwards(apps, schema_editor):
    User = apps.get_model("accounts", "CustomUser")
    EmailAddress = apps.get_model("account", "EmailAddress")

    existing_user_ids = set(
        EmailAddress.objects.values_list("user_id", flat=True),
    )
    to_create = [
        EmailAddress(
            user_id=u.id,
            email=u.email,
            verified=True,
            primary=True,
        )
        for u in User.objects.exclude(email="").exclude(email__isnull=True)
        if u.id not in existing_user_ids
    ]
    EmailAddress.objects.bulk_create(
        to_create,
        ignore_conflicts=True,
        batch_size=500,
    )


class Migration(migrations.Migration):
    dependencies = [
        (
            "accounts",
            "0004_rename_accounts_us_user_id_56e1b1_idx_accounts_us_user_id_1ff512_idx_and_more",
        ),
        ("account", "0009_emailaddress_unique_primary_email"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
