from unittest.mock import patch

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from notifications import channels, email, kinds, services
from notifications.models import Notification, NotificationPreference

User = get_user_model()


@override_settings(
    FRONTEND_URL="https://thps.run",
    ACCOUNT_EMAIL_SUBJECT_PREFIX="[thps.run] ",
)
class EmailHelperTests(TestCase):
    def test_subject_uses_per_kind_map_with_prefix(self) -> None:
        subject = email.build_subject(kinds.RUN_APPROVED, fallback_title="ignored")
        self.assertEqual(subject, "[thps.run] Run approved")

    def test_subject_falls_back_to_title_for_unmapped_kind(self) -> None:
        subject = email.build_subject("not_a_real_kind", fallback_title="A title")
        self.assertEqual(subject, "[thps.run] A title")

    def test_cta_url_run_approved_uses_game_slug(self) -> None:
        url = email.build_cta_url(
            kind=kinds.RUN_APPROVED,
            target_type="run",
            target_id="abc123",
            payload={"game_id": "thps3"},
        )
        self.assertEqual(url, "https://thps.run/thps3")

    def test_cta_url_run_approved_missing_game_id_falls_back_to_submissions(
        self,
    ) -> None:
        url = email.build_cta_url(
            kind=kinds.RUN_APPROVED,
            target_type="run",
            target_id="abc123",
            payload={},
        )
        self.assertEqual(url, "https://thps.run/submissions")

    def test_cta_url_run_denied_goes_to_submissions(self) -> None:
        url = email.build_cta_url(
            kind=kinds.RUN_DENIED,
            target_type="run",
            target_id="abc123",
            payload={"game_id": "thps3"},
        )
        self.assertEqual(url, "https://thps.run/submissions")

    def test_cta_url_run_review_goes_to_submissions(self) -> None:
        url = email.build_cta_url(
            kind=kinds.RUN_REVIEW,
            target_type="run",
            target_id="abc123",
            payload={"game_id": "thps3"},
        )
        self.assertEqual(url, "https://thps.run/submissions")

    def test_cta_url_mod_promoted_uses_game_manage_path(self) -> None:
        url = email.build_cta_url(
            kind=kinds.MOD_PROMOTED,
            target_type="game",
            target_id="thps3",
            payload={"game_id": "thps3"},
        )
        self.assertEqual(url, "https://thps.run/thps3/manage")

    def test_cta_url_api_key_expiring_uses_profile_settings(self) -> None:
        url = email.build_cta_url(
            kind=kinds.API_KEY_EXPIRING,
            target_type="api_key",
            target_id="42",
            payload={},
        )
        self.assertEqual(url, "https://thps.run/profile/settings/api-keys")

    def test_cta_url_user_data_export_ready_uses_danger_page(self) -> None:
        url = email.build_cta_url(
            kind=kinds.USER_DATA_EXPORT_READY,
            target_type="user_data_export",
            target_id="9",
            payload={},
        )
        self.assertEqual(url, "https://thps.run/profile/settings/danger")

    def test_cta_url_user_data_export_failed_uses_danger_page(self) -> None:
        url = email.build_cta_url(
            kind=kinds.USER_DATA_EXPORT_FAILED,
            target_type="user_data_export",
            target_id="9",
            payload={},
        )
        self.assertEqual(url, "https://thps.run/profile/settings/danger")

    def test_cta_url_user_data_export_group_uses_danger_page(self) -> None:
        url = email.build_cta_url(
            kind=kinds.USER_DATA_EXPORT_GROUP,
            target_type="user_data_export",
            target_id="9",
            payload={},
        )
        self.assertEqual(url, "https://thps.run/profile/settings/danger")

    def test_cta_url_unknown_kind_falls_back_to_target_type(self) -> None:
        url = email.build_cta_url(
            kind="not_a_real_kind",
            target_type="game",
            target_id="thps3",
            payload={},
        )
        self.assertEqual(url, "https://thps.run/thps3")

    def test_cta_url_unknown_kind_unknown_target_falls_back_to_frontend(self) -> None:
        url = email.build_cta_url(
            kind="not_a_real_kind",
            target_type="unknown",
            target_id="x",
            payload={},
        )
        self.assertEqual(url, "https://thps.run")

    def test_cta_url_unknown_kind_known_target_empty_id_falls_back_to_frontend(
        self,
    ) -> None:
        url = email.build_cta_url(
            kind="not_a_real_kind",
            target_type="game",
            target_id="",
            payload={},
        )
        self.assertEqual(url, "https://thps.run")

    def test_preferences_url(self) -> None:
        self.assertEqual(
            email.preferences_url(),
            "https://thps.run/profile/settings/notifications",
        )


class IsEnabledForTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="enabled-user", password="x")

    def test_default_in_app_is_true_when_no_pref(self) -> None:
        self.assertTrue(
            services._is_enabled_for(self.user.pk, kinds.RUN_APPROVED, channels.IN_APP),
        )

    def test_default_email_is_false_when_no_pref(self) -> None:
        self.assertFalse(
            services._is_enabled_for(self.user.pk, kinds.RUN_APPROVED, channels.EMAIL),
        )

    def test_explicit_in_app_pref_overrides_default(self) -> None:
        NotificationPreference.objects.create(
            user=self.user,
            type=kinds.RUN_APPROVED,
            channel=channels.IN_APP,
            enabled=False,
        )
        self.assertFalse(
            services._is_enabled_for(self.user.pk, kinds.RUN_APPROVED, channels.IN_APP),
        )

    def test_explicit_email_pref_overrides_default(self) -> None:
        NotificationPreference.objects.create(
            user=self.user,
            type=kinds.RUN_APPROVED,
            channel=channels.EMAIL,
            enabled=True,
        )
        self.assertTrue(
            services._is_enabled_for(self.user.pk, kinds.RUN_APPROVED, channels.EMAIL),
        )

    def test_group_pref_gates_member_kinds(self) -> None:
        NotificationPreference.objects.create(
            user=self.user,
            type=kinds.USER_DATA_EXPORT_GROUP,
            channel=channels.IN_APP,
            enabled=False,
        )
        self.assertFalse(
            services._is_enabled_for(
                self.user.pk,
                kinds.USER_DATA_EXPORT_READY,
                channels.IN_APP,
            ),
        )
        self.assertFalse(
            services._is_enabled_for(
                self.user.pk,
                kinds.USER_DATA_EXPORT_FAILED,
                channels.IN_APP,
            ),
        )

    def test_unknown_kind_returns_false(self) -> None:
        self.assertFalse(
            services._is_enabled_for(self.user.pk, "no_such_kind", channels.IN_APP),
        )


class DispatcherTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="disp-user", password="x")

    def _set_pref(self, kind: str, channel: str, enabled: bool) -> None:
        NotificationPreference.objects.update_or_create(
            user=self.user,
            type=kind,
            channel=channel,
            defaults={"enabled": enabled},
        )

    @patch("notifications.tasks.send_notification_email")
    def test_both_off_emits_nothing(self, mock_task) -> None:
        self._set_pref(kinds.RUN_APPROVED, channels.IN_APP, False)
        self._set_pref(kinds.RUN_APPROVED, channels.EMAIL, False)
        with self.captureOnCommitCallbacks(execute=True):
            result = services.create_notification(
                user=self.user,
                kind=kinds.RUN_APPROVED,
                title="t",
                body="b",
            )
        self.assertIsNone(result)
        self.assertFalse(Notification.objects.filter(user=self.user).exists())
        mock_task.delay.assert_not_called()

    @patch("notifications.tasks.send_notification_email")
    def test_in_app_only_writes_row_no_enqueue(self, mock_task) -> None:
        self._set_pref(kinds.RUN_APPROVED, channels.IN_APP, True)
        self._set_pref(kinds.RUN_APPROVED, channels.EMAIL, False)
        with self.captureOnCommitCallbacks(execute=True):
            services.create_notification(
                user=self.user,
                kind=kinds.RUN_APPROVED,
                title="t",
                body="b",
            )
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 1)
        mock_task.delay.assert_not_called()

    @patch("notifications.tasks.send_notification_email")
    def test_email_only_enqueues_no_row(self, mock_task) -> None:
        self._set_pref(kinds.RUN_APPROVED, channels.IN_APP, False)
        self._set_pref(kinds.RUN_APPROVED, channels.EMAIL, True)
        with self.captureOnCommitCallbacks(execute=True):
            result = services.create_notification(
                user=self.user,
                kind=kinds.RUN_APPROVED,
                title="t",
                body="b",
                target_type="run",
                target_id="abc",
                payload={"run_id": "abc"},
            )
        self.assertIsNone(result)
        self.assertFalse(Notification.objects.filter(user=self.user).exists())
        mock_task.delay.assert_called_once_with(
            user_id=self.user.pk,
            kind=kinds.RUN_APPROVED,
            title="t",
            body="b",
            target_type="run",
            target_id="abc",
            payload={"run_id": "abc"},
        )

    @patch("notifications.tasks.send_notification_email")
    def test_both_on_writes_row_and_enqueues(self, mock_task) -> None:
        self._set_pref(kinds.RUN_APPROVED, channels.IN_APP, True)
        self._set_pref(kinds.RUN_APPROVED, channels.EMAIL, True)
        with self.captureOnCommitCallbacks(execute=True):
            services.create_notification(
                user=self.user,
                kind=kinds.RUN_APPROVED,
                title="t",
                body="b",
            )
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 1)
        mock_task.delay.assert_called_once()

    def test_unknown_kind_raises(self) -> None:
        with self.assertRaises(ValueError):
            services.create_notification(
                user=self.user,
                kind="not_real",
                title="t",
            )

    def test_no_user_returns_none(self) -> None:
        result = services.create_notification(
            user=None,
            kind=kinds.RUN_APPROVED,
            title="t",
        )
        self.assertIsNone(result)


@override_settings(
    FRONTEND_URL="https://thps.run",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@thps.run",
    ACCOUNT_EMAIL_SUBJECT_PREFIX="[thps.run] ",
)
class SendNotificationEmailTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="recipient",
            email="recipient@example.com",
            password="x",
        )
        EmailAddress.objects.create(
            user=self.user,
            email="recipient@example.com",
            primary=True,
            verified=True,
        )
        mail.outbox = []

    def _send(self, **overrides) -> dict:
        from notifications.tasks import send_notification_email

        defaults = dict(
            user_id=self.user.pk,
            kind=kinds.RUN_APPROVED,
            title="Run approved",
            body="Your THPS3 Any% run was approved.",
            target_type="run",
            target_id="abc123",
            payload={"run_id": "abc123", "game_id": "thps3"},
        )
        defaults.update(overrides)
        return send_notification_email(**defaults)

    def test_skips_when_user_missing(self) -> None:
        result = self._send(user_id=99999)
        self.assertEqual(result, {"sent": 0, "skipped": "user_missing"})
        self.assertEqual(len(mail.outbox), 0)

    def test_skips_when_email_unverified(self) -> None:
        EmailAddress.objects.filter(user=self.user).update(verified=False)
        result = self._send()
        self.assertEqual(result, {"sent": 0, "skipped": "no_verified_email"})
        self.assertEqual(len(mail.outbox), 0)

    def test_skips_when_pref_flipped_off(self) -> None:
        NotificationPreference.objects.create(
            user=self.user,
            type=kinds.RUN_APPROVED,
            channel=channels.EMAIL,
            enabled=False,
        )
        result = self._send()
        self.assertEqual(result, {"sent": 0, "skipped": "pref_disabled"})
        self.assertEqual(len(mail.outbox), 0)

    def test_sends_with_correct_subject_and_cta(self) -> None:
        NotificationPreference.objects.create(
            user=self.user,
            type=kinds.RUN_APPROVED,
            channel=channels.EMAIL,
            enabled=True,
        )
        result = self._send()
        self.assertEqual(result, {"sent": 1})
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.subject, "[thps.run] Run approved")
        self.assertEqual(msg.to, ["recipient@example.com"])
        self.assertEqual(msg.from_email, "noreply@thps.run")
        self.assertIn("https://thps.run/thps3", msg.body)
        self.assertIn("Your THPS3 Any% run was approved.", msg.body)
        self.assertIn("https://thps.run/profile/settings/notifications", msg.body)

    def test_run_approved_without_game_id_falls_back_to_submissions(self) -> None:
        NotificationPreference.objects.create(
            user=self.user,
            type=kinds.RUN_APPROVED,
            channel=channels.EMAIL,
            enabled=True,
        )
        result = self._send(payload={})
        self.assertEqual(result, {"sent": 1})
        body = mail.outbox[0].body
        self.assertIn("https://thps.run/submissions", body)
        self.assertNotIn("/runs/", body)


class PreferencesApiTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="api-user", password="x")
        self.client.force_login(self.user)

    def test_get_returns_channels_with_defaults(self) -> None:
        resp = self.client.get("/api/v1/notifications/preferences")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        kinds_to_channels = {p["kind"]: p["channels"] for p in body["preferences"]}
        self.assertEqual(
            kinds_to_channels[kinds.RUN_APPROVED],
            {"in_app": True, "email": False},
        )

    def test_get_returns_stored_overrides(self) -> None:
        NotificationPreference.objects.create(
            user=self.user,
            type=kinds.RUN_APPROVED,
            channel=channels.EMAIL,
            enabled=True,
        )
        resp = self.client.get("/api/v1/notifications/preferences")
        body = resp.json()
        kinds_to_channels = {p["kind"]: p["channels"] for p in body["preferences"]}
        self.assertEqual(
            kinds_to_channels[kinds.RUN_APPROVED],
            {"in_app": True, "email": True},
        )

    def test_put_writes_per_channel_rows(self) -> None:
        resp = self.client.put(
            "/api/v1/notifications/preferences",
            data={
                "preferences": {
                    kinds.RUN_APPROVED: {"in_app": False, "email": True},
                },
            },
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        rows = dict(
            NotificationPreference.objects.filter(
                user=self.user,
                type=kinds.RUN_APPROVED,
            ).values_list("channel", "enabled"),
        )
        self.assertEqual(rows, {"in_app": False, "email": True})

    def test_put_partial_leaves_other_channel_untouched(self) -> None:
        NotificationPreference.objects.create(
            user=self.user,
            type=kinds.RUN_APPROVED,
            channel=channels.IN_APP,
            enabled=False,
        )
        resp = self.client.put(
            "/api/v1/notifications/preferences",
            data={"preferences": {kinds.RUN_APPROVED: {"email": True}}},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        rows = dict(
            NotificationPreference.objects.filter(
                user=self.user,
                type=kinds.RUN_APPROVED,
            ).values_list("channel", "enabled"),
        )
        self.assertEqual(rows, {"in_app": False, "email": True})

    def test_put_rejects_unknown_kind(self) -> None:
        resp = self.client.put(
            "/api/v1/notifications/preferences",
            data={"preferences": {"not_a_kind": {"email": True}}},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"], "unknown_notification_kind")

    def test_put_rejects_unknown_channel(self) -> None:
        resp = self.client.put(
            "/api/v1/notifications/preferences",
            data={
                "preferences": {
                    kinds.RUN_APPROVED: {"push": True},
                },
            },
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"], "unknown_notification_channel")

    def test_kinds_endpoint_returns_default_channels(self) -> None:
        resp = self.client.get("/api/v1/notifications/kinds")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        kinds_to_defaults = {k["kind"]: k["default_channels"] for k in body["kinds"]}
        self.assertEqual(
            kinds_to_defaults[kinds.RUN_APPROVED],
            {"in_app": True, "email": False},
        )
