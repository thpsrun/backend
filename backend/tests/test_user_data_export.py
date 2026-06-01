from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
import zipfile
from unittest.mock import MagicMock, patch

from api.permissions import session_only
from django.contrib.auth import get_user_model
from django.http import HttpRequest
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from ninja.errors import HttpError


class SessionOnlyDependencyTest(TestCase):

    def setUp(
        self,
    ) -> None:
        User = get_user_model()
        self.user = User.objects.create_user(  # type: ignore
            username="exporter",
            email="exporter@example.com",
            password="supersecret123",
        )

    def _make_request(
        self,
        x_api_key: str | None = None,
        authenticated: bool = True,
        method: str = "GET",
    ) -> HttpRequest:
        request = HttpRequest()
        request.method = method
        request.META["HTTP_HOST"] = "testserver"
        if x_api_key is not None:
            request.META["HTTP_X_API_KEY"] = x_api_key
        if authenticated:
            request.user = self.user
        else:
            anon = MagicMock()
            anon.is_authenticated = False
            request.user = anon
        return request

    def test_rejects_api_key_header(
        self,
    ) -> None:
        dep = session_only()
        request = self._make_request(x_api_key="any-value")
        with self.assertRaises(HttpError) as ctx:
            dep(request)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_allows_authenticated_session(
        self,
    ) -> None:
        dep = session_only()
        request = self._make_request()
        result = dep(request)
        self.assertEqual(result, self.user)

    def test_rejects_unauthenticated_session(
        self,
    ) -> None:
        dep = session_only()
        request = self._make_request(authenticated=False)
        with self.assertRaises(HttpError) as ctx:
            dep(request)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_capability_required_when_specified(
        self,
    ) -> None:
        dep = session_only("nonexistent.capability")
        request = self._make_request()
        with self.assertRaises(HttpError) as ctx:
            dep(request)
        self.assertEqual(ctx.exception.status_code, 403)


class UserDataExportModelTest(TestCase):

    def setUp(
        self,
    ) -> None:
        User = get_user_model()
        self.user = User.objects.create_user(  # type: ignore
            username="modeluser",
            email="modeluser@example.com",
            password="supersecret123",
        )

    def test_create_pending_export(
        self,
    ) -> None:
        from accounts.models import UserDataExport

        export = UserDataExport.objects.create(user=self.user)
        self.assertIsInstance(export.id, uuid.UUID)
        self.assertEqual(export.status, UserDataExport.Status.PENDING)
        self.assertIsNotNone(export.requested_at)
        self.assertIsNone(export.completed_at)
        self.assertIsNone(export.expires_at)
        self.assertEqual(export.file_path, "")
        self.assertIsNone(export.file_size_bytes)
        self.assertEqual(export.error_message, "")

    def test_status_choices(
        self,
    ) -> None:
        from accounts.models import UserDataExport

        self.assertEqual(UserDataExport.Status.PENDING, "PENDING")
        self.assertEqual(UserDataExport.Status.RUNNING, "RUNNING")
        self.assertEqual(UserDataExport.Status.READY, "READY")
        self.assertEqual(UserDataExport.Status.FAILED, "FAILED")
        self.assertEqual(UserDataExport.Status.EXPIRED, "EXPIRED")

    def test_ordering_is_newest_first(
        self,
    ) -> None:
        from accounts.models import UserDataExport

        older = UserDataExport.objects.create(user=self.user)
        older.requested_at = timezone.now() - timezone.timedelta(hours=2)
        older.save(update_fields=["requested_at"])
        UserDataExport.objects.create(user=self.user)
        results = list(UserDataExport.objects.filter(user=self.user))
        self.assertEqual(len(results), 2)
        self.assertGreater(results[0].requested_at, results[1].requested_at)


class ExportersTest(TestCase):

    def setUp(
        self,
    ) -> None:
        User = get_user_model()
        self.user = User.objects.create_user(  # type: ignore
            username="ex",
            email="ex@example.com",
            password="supersecret123",
        )

    def test_account_excludes_password_and_encrypted_api_key(
        self,
    ) -> None:
        from accounts.exporters import serialize_account

        rows = list(serialize_account(self.user))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertNotIn("password", row)
        self.assertNotIn("encrypted_api_key", row)
        self.assertEqual(row["username"], "ex")
        self.assertEqual(row["email"], "ex@example.com")

    def test_collect_exports_returns_every_entity(
        self,
    ) -> None:
        from accounts.exporters import collect_exports

        names = [name for name, _ in collect_exports(self.user)]
        self.assertEqual(
            names,
            [
                "account",
                "player",
                "runs",
                "run_history",
                "guides",
                "submissions",
                "api_keys",
                "api_activity_log",
                "notifications",
                "notification_preferences",
                "social_accounts",
                "game_audit_events",
            ],
        )

    def test_api_keys_excludes_hashed_secret(
        self,
    ) -> None:
        from accounts.exporters import serialize_api_keys
        from api.models import APIKey

        APIKey.objects.create_key(user=self.user, label="export-test-key")
        rows = list(serialize_api_keys(self.user))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertNotIn("hashed_key", row)
        self.assertNotIn("prefix", row)
        self.assertNotIn("id", row)
        self.assertEqual(row["label"], "export-test-key")

    def test_player_empty_when_unclaimed(
        self,
    ) -> None:
        from accounts.exporters import serialize_player

        rows = list(serialize_player(self.user))
        self.assertEqual(rows, [])

    def test_social_accounts_excludes_tokens(
        self,
    ) -> None:
        from accounts.exporters import serialize_social_accounts
        from allauth.socialaccount.models import SocialAccount

        SocialAccount.objects.create(
            user=self.user,
            provider="discord",
            uid="12345",
            extra_data={"username": "ex#1234"},
        )
        rows = list(serialize_social_accounts(self.user))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertNotIn("access_token", row)
        self.assertNotIn("refresh_token", row)
        self.assertNotIn("token_secret", row)
        self.assertEqual(row["provider"], "discord")
        self.assertEqual(row["uid"], "12345")


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="thpsrun-export-test-"))
class BuildUserDataExportTaskTest(TestCase):

    def setUp(
        self,
    ) -> None:
        User = get_user_model()
        self.user = User.objects.create_user(  # type: ignore
            username="taskuser",
            email="taskuser@example.com",
            password="supersecret123",
        )

    def test_happy_path_produces_zip_and_ready_row(
        self,
    ) -> None:
        from accounts.models import UserDataExport
        from accounts.tasks import build_user_data_export

        row = UserDataExport.objects.create(user=self.user)
        with patch("accounts.tasks.create_notification") as mock_notify:
            build_user_data_export(str(row.pk))
            mock_notify.assert_called_once()
        row.refresh_from_db()
        self.assertEqual(row.status, UserDataExport.Status.READY)
        self.assertIsNotNone(row.completed_at)
        self.assertIsNotNone(row.expires_at)
        self.assertGreater(row.file_size_bytes or 0, 0)

        from django.conf import settings as dj_settings

        full_path = os.path.join(dj_settings.MEDIA_ROOT, row.file_path)
        self.assertTrue(os.path.exists(full_path))

        with zipfile.ZipFile(full_path) as zf:
            names = zf.namelist()
            self.assertIn("manifest.json", names)
            self.assertIn("README.txt", names)
            self.assertIn("json/account.json", names)
            self.assertIn("csv/account.csv", names)

            manifest = json.loads(zf.read("manifest.json"))
            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["user_id"], self.user.pk)
            account_entry = next(
                e for e in manifest["files"] if e["path"] == "json/account.json"
            )
            digest = hashlib.sha256(zf.read("json/account.json")).hexdigest()
            self.assertEqual(account_entry["sha256"], digest)

    def test_failure_path_marks_failed_and_removes_tmp(
        self,
    ) -> None:
        from accounts.models import UserDataExport
        from accounts.tasks import build_user_data_export

        row = UserDataExport.objects.create(user=self.user)
        with patch(
            "accounts.tasks.collect_exports",
            side_effect=RuntimeError("kaboom"),
        ), patch("accounts.tasks.create_notification") as mock_notify:
            build_user_data_export(str(row.pk))
            mock_notify.assert_called_once()
        row.refresh_from_db()
        self.assertEqual(row.status, UserDataExport.Status.FAILED)
        self.assertIn("kaboom", row.error_message)

        from django.conf import settings as dj_settings

        tmp_path = os.path.join(dj_settings.MEDIA_ROOT, "exports", f"{row.pk}.zip.tmp")
        self.assertFalse(os.path.exists(tmp_path))

    def test_success_expires_prior_ready_row(
        self,
    ) -> None:
        from accounts.models import UserDataExport
        from accounts.tasks import build_user_data_export
        from django.conf import settings as dj_settings

        prior = UserDataExport.objects.create(user=self.user)
        prior.status = UserDataExport.Status.READY
        prior_path_rel = "exports/prior.zip"
        prior_path_abs = os.path.join(dj_settings.MEDIA_ROOT, prior_path_rel)
        os.makedirs(os.path.dirname(prior_path_abs), exist_ok=True)
        with open(prior_path_abs, "wb") as f:
            f.write(b"old export contents")
        prior.file_path = prior_path_rel
        prior.file_size_bytes = 19
        prior.save(update_fields=["status", "file_path", "file_size_bytes"])

        new_row = UserDataExport.objects.create(user=self.user)
        with patch("accounts.tasks.create_notification"):
            build_user_data_export(str(new_row.pk))

        prior.refresh_from_db()
        self.assertEqual(prior.status, UserDataExport.Status.EXPIRED)
        self.assertEqual(prior.file_path, "")
        self.assertFalse(os.path.exists(prior_path_abs))

        new_row.refresh_from_db()
        self.assertEqual(new_row.status, UserDataExport.Status.READY)
        new_path_abs = os.path.join(dj_settings.MEDIA_ROOT, new_row.file_path)
        self.assertTrue(os.path.exists(new_path_abs))


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="thpsrun-purge-test-"))
class PurgeExpiredExportsTaskTest(TestCase):

    def setUp(
        self,
    ) -> None:
        User = get_user_model()
        self.user = User.objects.create_user(  # type: ignore
            username="purgeuser",
            email="purgeuser@example.com",
            password="supersecret123",
        )

    def test_expired_ready_row_becomes_expired_and_file_removed(
        self,
    ) -> None:
        from accounts.models import UserDataExport
        from accounts.tasks import purge_expired_user_data_exports
        from django.conf import settings as dj_settings

        row = UserDataExport.objects.create(user=self.user)
        rel_path = f"exports/{row.pk}.zip"
        abs_path = os.path.join(dj_settings.MEDIA_ROOT, rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "wb") as f:
            f.write(b"stale")

        row.status = UserDataExport.Status.READY
        row.file_path = rel_path
        row.file_size_bytes = 5
        row.expires_at = timezone.now() - timezone.timedelta(seconds=10)
        row.save(update_fields=["status", "file_path", "file_size_bytes", "expires_at"])

        result = purge_expired_user_data_exports()
        self.assertEqual(result, {"expired": 1})

        row.refresh_from_db()
        self.assertEqual(row.status, UserDataExport.Status.EXPIRED)
        self.assertEqual(row.file_path, "")
        self.assertIsNone(row.file_size_bytes)
        self.assertFalse(os.path.exists(abs_path))

    def test_unexpired_row_untouched(
        self,
    ) -> None:
        from accounts.models import UserDataExport
        from accounts.tasks import purge_expired_user_data_exports

        row = UserDataExport.objects.create(user=self.user)
        row.status = UserDataExport.Status.READY
        row.expires_at = timezone.now() + timezone.timedelta(hours=1)
        row.file_path = "exports/nope.zip"
        row.file_size_bytes = 5
        row.save(update_fields=["status", "expires_at", "file_path", "file_size_bytes"])

        result = purge_expired_user_data_exports()
        self.assertEqual(result, {"expired": 0})
        row.refresh_from_db()
        self.assertEqual(row.status, UserDataExport.Status.READY)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="thpsrun-endpoint-test-"))
class DataExportEndpointTests(TestCase):

    def setUp(
        self,
    ) -> None:
        User = get_user_model()
        self.user = User.objects.create_user(  # type: ignore
            username="ep",
            email="ep@example.com",
            password="supersecret123",
        )
        self.other = User.objects.create_user(  # type: ignore
            username="other",
            email="other@example.com",
            password="supersecret123",
        )
        self.client = Client()

    # POST /me/export

    def test_post_creates_pending_row(
        self,
    ) -> None:
        from accounts.models import UserDataExport

        self.client.force_login(self.user)
        with patch(
            "api.v1.routers.auth.data_export.build_user_data_export.delay",
        ) as mock_delay:
            resp = self.client.post("/api/v1/auth/me/export")
        self.assertEqual(resp.status_code, 202)
        body = resp.json()
        self.assertEqual(body["status"], "PENDING")
        self.assertEqual(UserDataExport.objects.filter(user=self.user).count(), 1)
        mock_delay.assert_called_once()

    def test_post_within_24h_returns_429(
        self,
    ) -> None:
        from accounts.models import UserDataExport

        UserDataExport.objects.create(user=self.user)
        self.client.force_login(self.user)
        with patch(
            "api.v1.routers.auth.data_export.build_user_data_export.delay",
        ) as mock_delay:
            resp = self.client.post("/api/v1/auth/me/export")
        self.assertEqual(resp.status_code, 429)
        body = resp.json()
        self.assertIn("retry_after_seconds", body)
        self.assertGreater(body["retry_after_seconds"], 0)
        mock_delay.assert_not_called()

    def test_post_after_failed_within_24h_succeeds(
        self,
    ) -> None:
        from accounts.models import UserDataExport

        failed = UserDataExport.objects.create(user=self.user)
        failed.status = UserDataExport.Status.FAILED
        failed.save(update_fields=["status"])
        self.client.force_login(self.user)
        with patch("api.v1.routers.auth.data_export.build_user_data_export.delay"):
            resp = self.client.post("/api/v1/auth/me/export")
        self.assertEqual(resp.status_code, 202)

    def test_post_with_api_key_returns_403(
        self,
    ) -> None:
        from accounts.models import UserDataExport
        from api.models import APIKey

        _, raw = APIKey.objects.create_key(user=self.user, label="ep-key")
        resp = self.client.post(
            "/api/v1/auth/me/export",
            HTTP_X_API_KEY=raw,
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(UserDataExport.objects.filter(user=self.user).count(), 0)

    def test_post_unauthenticated_returns_401(
        self,
    ) -> None:
        resp = self.client.post("/api/v1/auth/me/export")
        self.assertEqual(resp.status_code, 401)

    # GET /me/exports

    def test_list_returns_only_own(
        self,
    ) -> None:
        from accounts.models import UserDataExport

        UserDataExport.objects.create(user=self.user)
        UserDataExport.objects.create(user=self.other)
        self.client.force_login(self.user)
        resp = self.client.get("/api/v1/auth/me/exports")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(len(body["exports"]), 1)

    def test_list_with_api_key_returns_403(
        self,
    ) -> None:
        from api.models import APIKey

        _, raw = APIKey.objects.create_key(user=self.user, label="list-key")
        resp = self.client.get(
            "/api/v1/auth/me/exports",
            HTTP_X_API_KEY=raw,
        )
        self.assertEqual(resp.status_code, 403)

    # GET /me/exports/{id}/download

    def _make_ready_export(
        self,
        owner,
        body: bytes = b"zipdata",
    ):
        from accounts.models import UserDataExport
        from django.conf import settings as dj_settings

        row = UserDataExport.objects.create(user=owner)
        rel = f"exports/{row.pk}.zip"
        abs_path = os.path.join(dj_settings.MEDIA_ROOT, rel)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "wb") as f:
            f.write(body)
        row.status = UserDataExport.Status.READY
        row.file_path = rel
        row.file_size_bytes = len(body)
        row.expires_at = timezone.now() + timezone.timedelta(days=7)
        row.completed_at = timezone.now()
        row.save()
        return row

    def test_download_serves_file_for_owner(
        self,
    ) -> None:
        row = self._make_ready_export(self.user, body=b"hello-world")
        self.client.force_login(self.user)
        resp = self.client.get(f"/api/v1/auth/me/exports/{row.pk}/download")
        self.assertEqual(resp.status_code, 200)
        content = b"".join(resp.streaming_content)
        self.assertEqual(content, b"hello-world")
        self.assertIn("attachment", resp["Content-Disposition"])

    def test_download_other_user_returns_404(
        self,
    ) -> None:
        row = self._make_ready_export(self.other)
        self.client.force_login(self.user)
        resp = self.client.get(f"/api/v1/auth/me/exports/{row.pk}/download")
        self.assertEqual(resp.status_code, 404)

    def test_download_not_ready_returns_404(
        self,
    ) -> None:
        from accounts.models import UserDataExport

        row = UserDataExport.objects.create(user=self.user)
        self.client.force_login(self.user)
        resp = self.client.get(f"/api/v1/auth/me/exports/{row.pk}/download")
        self.assertEqual(resp.status_code, 404)

    def test_download_expired_returns_404(
        self,
    ) -> None:
        row = self._make_ready_export(self.user)
        row.expires_at = timezone.now() - timezone.timedelta(seconds=1)
        row.save(update_fields=["expires_at"])
        self.client.force_login(self.user)
        resp = self.client.get(f"/api/v1/auth/me/exports/{row.pk}/download")
        self.assertEqual(resp.status_code, 404)

    def test_download_with_api_key_returns_403(
        self,
    ) -> None:
        row = self._make_ready_export(self.user)
        from api.models import APIKey

        _, raw = APIKey.objects.create_key(user=self.user, label="dl-key")
        resp = self.client.get(
            f"/api/v1/auth/me/exports/{row.pk}/download",
            HTTP_X_API_KEY=raw,
        )
        self.assertEqual(resp.status_code, 403)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="thpsrun-privacy-test-"))
class PrivacyAssertionTest(TestCase):

    def setUp(
        self,
    ) -> None:
        User = get_user_model()
        self.user = User.objects.create_user(  # type: ignore
            username="privuser",
            email="privuser@example.com",
            password="UNIQUE-PASSWORD-VALUE-XYZ",
        )

    def test_zip_contains_no_password_or_tokens(
        self,
    ) -> None:
        from accounts.models import UserDataExport
        from accounts.tasks import build_user_data_export
        from allauth.socialaccount.models import SocialAccount, SocialApp, SocialToken
        from api.models import APIKey

        APIKey.objects.create_key(user=self.user, label="priv-key")

        app = SocialApp.objects.create(
            provider="discord",
            name="discord-test",
            client_id="x",
            secret="y",
        )
        sa = SocialAccount.objects.create(
            user=self.user,
            provider="discord",
            uid="42",
            extra_data={"username": "privuser#0001"},
        )
        SocialToken.objects.create(
            app=app,
            account=sa,
            token="OAUTH-ACCESS-TOKEN-SHOULD-NOT-LEAK",
            token_secret="OAUTH-REFRESH-TOKEN-SHOULD-NOT-LEAK",
        )

        row = UserDataExport.objects.create(user=self.user)
        with patch("accounts.tasks.create_notification"):
            build_user_data_export(str(row.pk))
        row.refresh_from_db()

        from django.conf import settings as dj_settings

        full_path = os.path.join(dj_settings.MEDIA_ROOT, row.file_path)
        forbidden = [
            b"UNIQUE-PASSWORD-VALUE-XYZ",
            b"OAUTH-ACCESS-TOKEN-SHOULD-NOT-LEAK",
            b"OAUTH-REFRESH-TOKEN-SHOULD-NOT-LEAK",
        ]
        with zipfile.ZipFile(full_path) as zf:
            for name in zf.namelist():
                if name in ("manifest.json", "README.txt"):
                    continue
                contents = zf.read(name)
                for needle in forbidden:
                    self.assertNotIn(
                        needle,
                        contents,
                        msg=f"Forbidden value {needle!r} found in {name}",
                    )
