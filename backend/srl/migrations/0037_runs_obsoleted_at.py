from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("srl", "0036_alter_categories_game_alter_games_slug_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="runs",
            name="obsoleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="runhistory",
            name="streak_start_date",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Streak Start (WR entries only)",
            ),
        ),
    ]
