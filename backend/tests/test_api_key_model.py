from datetime import timedelta

from api.models import APIKey
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from srl.models import Games

User = get_user_model()


class APIKeyModelTest(TestCase):
    @classmethod
    def setUpTestData(
        cls,
    ) -> None:
        cls.user = User.objects.create_user(
            username="alice",
            email="alice@example.com",
            password="testpass123",
        )
        cls.inactive_user = User.objects.create_user(
            username="ghost",
            email="ghost@example.com",
            password="testpass123",
            is_active=False,
        )
        cls.game = Games.objects.create(
            id="g-apikey",
            name="API Key Game",
            slug="api-key-game",
            twitch="API Key Game",
            release="2000-01-01",
            boxart="https://example.com/cover",
            defaulttime="realtime",
            idefaulttime="realtime",
            pointsmax=1000,
            ipointsmax=100,
        )

    def test_apikey_has_user_fk(
        self,
    ) -> None:
        key_obj, _raw = APIKey.objects.create_key(
            user=self.user,
            label="test",
        )
        self.assertEqual(key_obj.user, self.user)

    def test_apikey_label_required(
        self,
    ) -> None:
        key_obj, _raw = APIKey.objects.create_key(
            user=self.user,
            label="my key",
        )
        self.assertEqual(key_obj.label, "my key")

    def test_apikey_default_scope_is_empty(
        self,
    ) -> None:
        key_obj, _raw = APIKey.objects.create_key(
            user=self.user,
            label="unrestricted",
        )
        self.assertEqual(list(key_obj.scope_games.all()), [])
        self.assertEqual(key_obj.scope_capabilities, [])

    def test_apikey_scope_games_m2m(
        self,
    ) -> None:
        key_obj, _raw = APIKey.objects.create_key(
            user=self.user,
            label="scoped",
        )
        key_obj.scope_games.add(self.game)
        self.assertIn(self.game, key_obj.scope_games.all())

    def test_apikey_scope_capabilities_array(
        self,
    ) -> None:
        key_obj, _raw = APIKey.objects.create_key(
            user=self.user,
            label="runs only",
            scope_capabilities=["runs.verify"],
        )
        self.assertEqual(key_obj.scope_capabilities, ["runs.verify"])

    def test_apikey_related_name_reverse_lookup(
        self,
    ) -> None:
        key_obj, _raw = APIKey.objects.create_key(
            user=self.user,
            label="reverse",
        )
        self.assertIn(key_obj, self.user.api_keys.all())

    def test_apikey_game_deletion_cleans_m2m(
        self,
    ) -> None:
        key_obj, _raw = APIKey.objects.create_key(
            user=self.user,
            label="game-scoped",
        )
        key_obj.scope_games.add(self.game)
        self.game.delete()
        key_obj.refresh_from_db()
        self.assertEqual(list(key_obj.scope_games.all()), [])

    def test_get_usable_keys_excludes_inactive_user_owner(
        self,
    ) -> None:
        key_obj, _raw = APIKey.objects.create_key(
            user=self.inactive_user,
            label="inactive-owner",
        )
        self.assertFalse(
            APIKey.objects.get_usable_keys().filter(pk=key_obj.pk).exists(),
        )

    def test_get_usable_keys_excludes_revoked(
        self,
    ) -> None:
        key_obj, _raw = APIKey.objects.create_key(
            user=self.user,
            label="revoked-key",
        )
        key_obj.revoked = True
        key_obj.revoked_reason = "user"
        key_obj.save()
        self.assertFalse(
            APIKey.objects.get_usable_keys().filter(pk=key_obj.pk).exists(),
        )

    def test_get_usable_keys_excludes_expired(
        self,
    ) -> None:
        key_obj, _raw = APIKey.objects.create_key(
            user=self.user,
            label="expired-key",
            expiry_date=timezone.now() - timedelta(days=1),
        )
        self.assertFalse(
            APIKey.objects.get_usable_keys().filter(pk=key_obj.pk).exists(),
        )

    def test_get_usable_keys_includes_active_key(
        self,
    ) -> None:
        key_obj, _raw = APIKey.objects.create_key(
            user=self.user,
            label="active-key",
        )
        self.assertTrue(
            APIKey.objects.get_usable_keys().filter(pk=key_obj.pk).exists(),
        )

    def test_revoked_reason_choices_accept_empty(
        self,
    ) -> None:
        key_obj, _raw = APIKey.objects.create_key(
            user=self.user,
            label="fresh",
        )
        self.assertEqual(key_obj.revoked_reason, "")

    def test_str_representation(
        self,
    ) -> None:
        key_obj, _raw = APIKey.objects.create_key(
            user=self.user,
            label="test label",
        )
        self.assertIn("test label", str(key_obj))
