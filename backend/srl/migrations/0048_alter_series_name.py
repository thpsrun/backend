from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("srl", "0047_games_verbose_recalc_log"),
    ]

    operations = [
        migrations.AlterField(
            model_name="series",
            name="name",
            field=models.CharField(max_length=80, verbose_name="Name"),
        ),
    ]
