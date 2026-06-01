import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("srl", "0040_srcsynctask_error_category_alter_srcsynctask_action"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ReconciliationJob",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "scope",
                    models.CharField(
                        choices=[
                            ("RUN", "Run"),
                            ("LEADERBOARD", "Leaderboard"),
                            ("GAME", "Game"),
                        ],
                        max_length=16,
                    ),
                ),
                ("target_id", models.CharField(blank=True, max_length=128)),
                ("target_descriptor", models.JSONField(blank=True, default=dict)),
                (
                    "source_of_truth",
                    models.CharField(
                        choices=[("SRC", "Speedrun.com"), ("THPS_RUN", "thps.run")],
                        default="SRC",
                        max_length=16,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("RUNNING", "Running"),
                            ("SUCCEEDED", "Succeeded"),
                            ("FAILED", "Failed"),
                            ("CANCELLED", "Cancelled"),
                        ],
                        default="PENDING",
                        max_length=16,
                    ),
                ),
                (
                    "phase",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("P1", "Phase 1: current state"),
                            ("P2", "Phase 2: obsolete backfill"),
                            ("P3", "Phase 3: recompute"),
                        ],
                        default="PENDING",
                        max_length=8,
                    ),
                ),
                ("cancel_requested", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("counts_created", models.IntegerField(default=0)),
                ("counts_updated", models.IntegerField(default=0)),
                ("counts_skipped", models.IntegerField(default=0)),
                ("counts_failed", models.IntegerField(default=0)),
                ("error_summary", models.TextField(blank=True, default="")),
                (
                    "celery_task_id",
                    models.CharField(blank=True, default="", max_length=128),
                ),
                ("pending_children", models.IntegerField(default=0)),
                ("failure_count", models.IntegerField(default=0)),
                (
                    "requested_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reconciliation_jobs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="ReconciliationItem",
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
                ("record_type", models.CharField(max_length=64)),
                ("record_id", models.CharField(max_length=128)),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("CREATED", "Created"),
                            ("UPDATED", "Updated"),
                            ("SKIPPED_LOCAL_WINS", "Skipped (local wins)"),
                            ("SKIPPED_NO_CHANGE", "Skipped (no change)"),
                            ("FAILED", "Failed"),
                        ],
                        max_length=32,
                    ),
                ),
                (
                    "phase",
                    models.CharField(
                        choices=[
                            ("P1", "Phase 1"),
                            ("P2", "Phase 2"),
                            ("P3", "Phase 3"),
                        ],
                        max_length=2,
                    ),
                ),
                ("changes", models.JSONField(blank=True, default=dict)),
                ("error", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="srl.reconciliationjob",
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="reconciliationjob",
            index=models.Index(
                fields=["scope", "target_id", "status"],
                name="srl_reconci_scope_8c1b6f_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="reconciliationjob",
            index=models.Index(
                fields=["-created_at"], name="srl_reconci_created_df7ba8_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="reconciliationitem",
            index=models.Index(
                fields=["job", "action"], name="srl_reconci_job_id_21e7db_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="reconciliationitem",
            index=models.Index(
                fields=["job", "phase"], name="srl_recon_item_job_phase_idx"
            ),
        ),
    ]
