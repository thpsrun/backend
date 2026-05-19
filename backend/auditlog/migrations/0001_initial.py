import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("api", "0007_alter_apiactivitylog_options"),
        ("srl", "0047_games_verbose_recalc_log"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="GameAuditEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("timing_config_change", "Timing Config Change"),
                            ("recalc_dispatch", "Recalc Dispatch"),
                            ("recalc_board", "Recalc Board Complete"),
                            ("run_recalc", "Run Recalc"),
                            ("src_sync_attempt", "SRC Sync Attempt"),
                            ("moderator_added", "Moderator Added"),
                            ("moderator_removed", "Moderator Removed"),
                            ("apikey_revoked", "API Key Revoked"),
                        ],
                        max_length=32,
                    ),
                ),
                (
                    "actor_kind",
                    models.CharField(
                        choices=[
                            ("user", "User"),
                            ("api_key", "API Key"),
                            ("system", "System"),
                        ],
                        default="system",
                        max_length=16,
                    ),
                ),
                (
                    "actor_label",
                    models.CharField(blank=True, default="", max_length=128),
                ),
                ("target_app", models.CharField(blank=True, default="", max_length=64)),
                (
                    "target_model",
                    models.CharField(blank=True, default="", max_length=64),
                ),
                ("target_id", models.CharField(blank=True, default="", max_length=64)),
                (
                    "target_repr",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                ("summary", models.CharField(max_length=255)),
                ("payload", models.JSONField(blank=True, null=True)),
                (
                    "game_slug_snapshot",
                    models.CharField(blank=True, max_length=255, null=True),
                ),
                (
                    "actor_api_key",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="api.apikey",
                    ),
                ),
                (
                    "actor_user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="game_audit_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "game",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_events",
                        to="srl.games",
                    ),
                ),
            ],
            options={
                "verbose_name": "Game Audit Entry",
                "verbose_name_plural": "Game Audit Events",
                "ordering": ("-created_at",),
                "indexes": [
                    models.Index(
                        fields=["game", "-created_at"],
                        name="audit_game_cr_idx",
                    ),
                    models.Index(
                        fields=["game", "event_type", "-created_at"],
                        name="audit_game_type_cr_idx",
                    ),
                    models.Index(
                        fields=["game", "actor_user", "-created_at"],
                        name="audit_game_user_cr_idx",
                    ),
                    models.Index(
                        fields=["game", "target_model", "-created_at"],
                        name="auditevent_game_target_idx",
                    ),
                    models.Index(
                        fields=["game_slug_snapshot", "-created_at"],
                        name="audit_orphan_slug_cr_idx",
                        condition=Q(game__isnull=True),
                    ),
                ],
            },
        ),
    ]
