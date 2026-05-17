from api.models import APIKey
from api.permissions import authed, public_read
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase
from django.utils import timezone
from ninja.errors import HttpError
from srl.models import Categories, CountryCodes, Games, Platforms, Players, Runs

User = get_user_model()


def run_target_resolver_factory(run: Runs):
    def _resolver(
        _request,
    ) -> Runs:
        return run

    return _resolver


class AuthedDependencyTest(TestCase):
    @classmethod
    def setUpTestData(
        cls,
    ) -> None:
        cls.factory = RequestFactory()
        cls.country = CountryCodes.objects.create(id="usa", name="United States")
        cls.platform = Platforms.objects.create(id="pc", name="PC", slug="pc")

        cls.game = Games.objects.create(
            id="auth-g",
            name="Authed Game",
            slug="auth-game",
            twitch="Authed Game",
            release="2000-01-01",
            boxart="https://example.com/c",
            defaulttime="rta",
            idefaulttime="rta",
            pointsmax=1000,
            ipointsmax=100,
        )
        cls.other_game = Games.objects.create(
            id="auth-og",
            name="Other Authed Game",
            slug="auth-og",
            twitch="Other Authed Game",
            release="2001-01-01",
            boxart="https://example.com/c2",
            defaulttime="rta",
            idefaulttime="rta",
            pointsmax=1000,
            ipointsmax=100,
        )
        cls.category = Categories.objects.create(
            id="auth-cat",
            game=cls.game,
            name="Any%",
            slug="any-auth",
            type="per-game",
            url="https://speedrun.com/",
            archive=False,
        )

        cls.super_user = User.objects.create_superuser(
            username="authsuper",
            email="authsuper@example.com",
            password="testpass123",
        )
        cls.regular_user = User.objects.create_user(
            username="authregular",
            email="authregular@example.com",
            password="testpass123",
        )
        cls.mod_user = User.objects.create_user(
            username="authmod",
            email="authmod@example.com",
            password="testpass123",
        )
        cls.mod_player = Players.objects.create(
            id="authmodp",
            name="authmodp",
            url="https://speedrun.com/",
            countrycode=cls.country,
            ex_stream=False,
            claim_status=Players.ClaimStatus.CLAIMED,
            user=cls.mod_user,
        )
        cls.game.moderators.add(cls.mod_player)

        cls.test_run = Runs.objects.create(
            id="auth-run",
            runtype="main",
            game=cls.game,
            category=cls.category,
            place=1,
            url="https://speedrun.com/auth-run",
            date=timezone.now(),
            v_date=timezone.now(),
            time="1m 00s",
            time_secs=60.0,
            points=1000,
            platform=cls.platform,
            emulated=False,
            vid_status="verified",
            obsolete=False,
        )

    def test_401_when_no_credential_present(
        self,
    ) -> None:
        request = self.factory.get("/")
        request.user = AnonymousUser()
        dep = authed("runs.submit")
        with self.assertRaises(HttpError) as ctx:
            dep(request)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_403_when_user_lacks_permission(
        self,
    ) -> None:
        request = self.factory.get("/")
        request.user = self.regular_user
        dep = authed(
            "runs.verify",
            target_resolver=run_target_resolver_factory(self.test_run),
        )
        with self.assertRaises(HttpError) as ctx:
            dep(request)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_mod_allowed_on_own_game(
        self,
    ) -> None:
        request = self.factory.get("/")
        request.user = self.mod_user
        dep = authed(
            "runs.verify",
            target_resolver=run_target_resolver_factory(self.test_run),
        )
        self.assertEqual(dep(request), self.mod_user)
        self.assertIsNone(getattr(request, "api_key", None))

    def test_api_key_no_scope_allows_authorized_action(
        self,
    ) -> None:
        key_obj, raw = APIKey.objects.create_key(
            user=self.super_user,
            label="admin-key",
        )
        request = self.factory.get("/", HTTP_X_API_KEY=raw)
        request.user = AnonymousUser()
        dep = authed("api_keys.admin")
        self.assertEqual(dep(request), self.super_user)
        self.assertEqual(request.api_key.pk, key_obj.pk)

    def test_invalid_api_key_returns_401(
        self,
    ) -> None:
        request = self.factory.get("/", HTTP_X_API_KEY="not-a-real-key")
        request.user = AnonymousUser()
        dep = authed("runs.submit")
        with self.assertRaises(HttpError) as ctx:
            dep(request)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_revoked_key_returns_401(
        self,
    ) -> None:
        key_obj, raw = APIKey.objects.create_key(
            user=self.super_user,
            label="revoked",
        )
        key_obj.revoked = True
        key_obj.revoked_reason = "user"
        key_obj.save()
        request = self.factory.get("/", HTTP_X_API_KEY=raw)
        request.user = AnonymousUser()
        dep = authed("api_keys.admin")
        with self.assertRaises(HttpError) as ctx:
            dep(request)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_inactive_owner_key_returns_401(
        self,
    ) -> None:
        ghost = User.objects.create_user(
            username="ghost-owner",
            email="ghost-owner@example.com",
            password="x",
            is_active=False,
        )
        key_obj, raw = APIKey.objects.create_key(
            user=ghost,
            label="ghost-key",
        )
        request = self.factory.get("/", HTTP_X_API_KEY=raw)
        request.user = AnonymousUser()
        dep = authed("api_keys.list_own")
        with self.assertRaises(HttpError) as ctx:
            dep(request)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_key_capability_scope_denies_out_of_scope(
        self,
    ) -> None:
        key_obj, raw = APIKey.objects.create_key(
            user=self.super_user,
            label="narrow-cap",
            scope_capabilities=["users.admin"],
        )
        request = self.factory.get("/", HTTP_X_API_KEY=raw)
        request.user = AnonymousUser()
        dep = authed("api_keys.admin")
        with self.assertRaises(HttpError) as ctx:
            dep(request)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_key_capability_scope_admits_listed(
        self,
    ) -> None:
        key_obj, raw = APIKey.objects.create_key(
            user=self.super_user,
            label="narrow-cap",
            scope_capabilities=["api_keys.admin"],
        )
        request = self.factory.get("/", HTTP_X_API_KEY=raw)
        request.user = AnonymousUser()
        dep = authed("api_keys.admin")
        self.assertEqual(dep(request), self.super_user)

    def test_key_game_scope_denies_out_of_scope_game(
        self,
    ) -> None:
        key_obj, raw = APIKey.objects.create_key(
            user=self.mod_user,
            label="other-only",
        )
        key_obj.scope_games.add(self.other_game)
        request = self.factory.get("/", HTTP_X_API_KEY=raw)
        request.user = AnonymousUser()
        dep = authed(
            "runs.verify",
            target_resolver=run_target_resolver_factory(self.test_run),
        )
        with self.assertRaises(HttpError) as ctx:
            dep(request)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_key_game_scope_admits_matching_game(
        self,
    ) -> None:
        key_obj, raw = APIKey.objects.create_key(
            user=self.mod_user,
            label="own-only",
        )
        key_obj.scope_games.add(self.game)
        request = self.factory.get("/", HTTP_X_API_KEY=raw)
        request.user = AnonymousUser()
        dep = authed(
            "runs.verify",
            target_resolver=run_target_resolver_factory(self.test_run),
        )
        self.assertEqual(dep(request), self.mod_user)

    def test_game_scoped_cap_with_no_target_and_scoped_key_denies(
        self,
    ) -> None:
        key_obj, raw = APIKey.objects.create_key(
            user=self.mod_user,
            label="game-scoped",
        )
        key_obj.scope_games.add(self.game)
        request = self.factory.get("/", HTTP_X_API_KEY=raw)
        request.user = AnonymousUser()
        dep = authed("runs.verify")  # no target_resolver
        with self.assertRaises(HttpError) as ctx:
            dep(request)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_non_scoped_capability_ignores_scope_games(
        self,
    ) -> None:
        key_obj, raw = APIKey.objects.create_key(
            user=self.super_user,
            label="admin-narrow",
        )
        key_obj.scope_games.add(self.other_game)
        request = self.factory.get("/", HTTP_X_API_KEY=raw)
        request.user = AnonymousUser()
        dep = authed("api_keys.admin")
        self.assertEqual(dep(request), self.super_user)


class PublicReadTest(TestCase):
    def setUp(
        self,
    ) -> None:
        self.factory = RequestFactory()

    def test_anon_returns_anonymous_user(
        self,
    ) -> None:
        request = self.factory.get("/")
        request.user = AnonymousUser()
        dep = public_read()
        result = dep(request)
        self.assertIsNotNone(result)
        self.assertFalse(result.is_authenticated)

    def test_authenticated_returns_user(
        self,
    ) -> None:
        user = User.objects.create_user(
            username="pr",
            email="pr@example.com",
            password="x",
        )
        request = self.factory.get("/")
        request.user = user
        dep = public_read()
        self.assertEqual(dep(request), user)
