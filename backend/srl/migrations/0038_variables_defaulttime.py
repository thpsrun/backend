from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("srl", "0037_runs_obsoleted_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="variables",
            name="defaulttime",
            field=models.CharField(
                blank=True,
                choices=[
                    ("realtime", "RTA"),
                    ("realtime_noloads", "LRT"),
                    ("ingame", "IGT"),
                ],
                default=None,
                help_text=(
                    "When not set, the variable inherits its category's timing method (or the "
                    "game's if the category does not set one). When set, this takes precedence "
                    "over both the category and game timing for any run that includes this "
                    "variable. Precedence: Variable > Category > Game."
                ),
                null=True,
                verbose_name="Default Time",
            ),
        ),
        migrations.AlterField(
            model_name="runs",
            name="obsoleted_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Should only be occupied if `obsolte` is true.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="variablevalues",
            name="defaulttime",
            field=models.CharField(
                blank=True,
                choices=[
                    ("realtime", "RTA"),
                    ("realtime_noloads", "LRT"),
                    ("ingame", "IGT"),
                ],
                default=None,
                help_text=(
                    "When not set, the value inherits its variable's timing method (or "
                    "further up the chain). When set, this is the most specific override "
                    "and takes precedence over the parent variable, the category, and the "
                    "game. Precedence: VariableValue > Variable > Category > Game."
                ),
                null=True,
                verbose_name="Default Time",
            ),
        ),
    ]
