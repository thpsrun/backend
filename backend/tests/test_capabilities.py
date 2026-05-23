from api.permissions import (
    ADMIN_ONLY_CAPABILITIES,
    CAPABILITY_SCOPED,
    SESSION_ONLY_CAPABILITIES,
)
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from django.utils import timezone
from rules.permissions import has_perm, perm_exists
from srl.models import (
    Categories,
    CountryCodes,
    Games,
    Platforms,
    Players,
    RunPlayers,
    Runs,
)

User = get_user_model()


ALL_CAPS: list[str] = [
    "runs.submit",
    "runs.edit_own",
    "runs.edit_any",
    "runs.verify",
    "runs.delete",
    "guides.create",
    "guides.edit_own",
    "guides.edit_any",
    "guides.delete_own",
    "guides.delete_any",
    "games.manage",
    "api_keys.create_own",
    "api_keys.list_own",
    "api_keys.revoke_own",
    "api_keys.admin",
    "users.admin",
]


class CapabilityRegistryShapeTest(TestCase):
    def test_every_capability_is_registered(
        self,
    ) -> None:
        for cap in ALL_CAPS:
            self.assertTrue(
                perm_exists(cap),
                f"capability {cap!r} is not registered",
            )

    def test_every_capability_has_registry_entry(
        self,
    ) -> None:
        known = (
            set(CAPABILITY_SCOPED)
            | set(SESSION_ONLY_CAPABILITIES)
            | set(ADMIN_ONLY_CAPABILITIES)
        )
        for cap in ALL_CAPS:
            self.assertIn(
                cap,
                known,
                f"capability {cap!r} missing from CAPABILITY_SCOPED, "
                "SESSION_ONLY_CAPABILITIES, and ADMIN_ONLY_CAPABILITIES",
            )

    def test_registry_tiers_are_disjoint(
        self,
    ) -> None:
        tiers = {
            "CAPABILITY_SCOPED": set(CAPABILITY_SCOPED),
            "SESSION_ONLY_CAPABILITIES": set(SESSION_ONLY_CAPABILITIES),
            "ADMIN_ONLY_CAPABILITIES": set(ADMIN_ONLY_CAPABILITIES),
        }
        for a, b in (
            ("CAPABILITY_SCOPED", "SESSION_ONLY_CAPABILITIES"),
            ("CAPABILITY_SCOPED", "ADMIN_ONLY_CAPABILITIES"),
            ("SESSION_ONLY_CAPABILITIES", "ADMIN_ONLY_CAPABILITIES"),
        ):
            overlap = tiers[a] & tiers[b]
            self.assertEqual(
                overlap,
                set(),
                f"caps appear in both {a} and {b}: {sorted(overlap)}",
            )


class CapabilityEvaluationTest(TestCase):
    @classmethod
    def setUpTestData(
        cls,
    ) -> None:
        cls.country = CountryCodes.objects.create(id="usa", name="United States")
        cls.platform = Platforms.objects.create(id="pc", name="PC", slug="pc")

        cls.game = Games.objects.create(
            id="thps2-cap",
            name="THPS2 Cap",
            slug="thps2-cap",
            twitch="THPS2",
            release="2000-01-01",
            boxart="https://example.com/c1",
            defaulttime="rta",
            idefaulttime="rta",
            pointsmax=1000,
            ipointsmax=100,
        )
        cls.other_game = Games.objects.create(
            id="thps1-cap",
            name="THPS1 Cap",
            slug="thps1-cap",
            twitch="THPS1",
            release="1999-01-01",
            boxart="https://example.com/c2",
            defaulttime="rta",
            idefaulttime="rta",
            pointsmax=1000,
            ipointsmax=100,
        )
        cls.category = Categories.objects.create(
            id="cat-cap",
            game=cls.game,
            name="Any%",
            slug="any-cap",
            type="per-game",
            url="https://speedrun.com/cap",
            archive=False,
        )

        cls.super_user = User.objects.create_superuser(
            username="capadmin",
            email="capadmin@example.com",
            password="testpass123",
        )
        cls.regular_user = User.objects.create_user(
            username="capregular",
            email="capregular@example.com",
            password="testpass123",
        )
        cls.mod_user = User.objects.create_user(
            username="capmod",
            email="capmod@example.com",
            password="testpass123",
        )
        cls.mod_player = Players.objects.create(
            id="capmodp",
            name="capmodp",
            url="https://speedrun.com/",
            countrycode=cls.country,
            ex_stream=False,
            claim_status=Players.ClaimStatus.CLAIMED,
            user=cls.mod_user,
        )
        cls.game.moderators.add(cls.mod_player)

        cls.test_run = Runs.objects.create(
            id="cap-run",
            runtype="main",
            game=cls.game,
            category=cls.category,
            place=1,
            url="https://speedrun.com/cap-run",
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

    def test_anon_denied_every_capability(
        self,
    ) -> None:
        for cap in ALL_CAPS:
            self.assertFalse(
                has_perm(cap, AnonymousUser()),
                f"{cap} should deny anon",
            )

    def test_runs_verify_allowed_on_own_game(
        self,
    ) -> None:
        self.assertTrue(self.mod_user.has_perm("runs.verify", self.test_run))

    def test_runs_verify_denied_on_other_game(
        self,
    ) -> None:
        other_run = Runs.objects.create(
            id="cap-run-o",
            runtype="main",
            game=self.other_game,
            category=self.category,
            place=1,
            url="https://speedrun.com/cap-run-other",
            date=timezone.now(),
            v_date=timezone.now(),
            time="1m 00s",
            time_secs=60.0,
            points=1000,
            platform=self.platform,
            emulated=False,
            vid_status="verified",
            obsolete=False,
        )
        self.assertFalse(self.mod_user.has_perm("runs.verify", other_run))

    def test_runs_verify_allowed_for_superuser_on_any_game(
        self,
    ) -> None:
        self.assertTrue(self.super_user.has_perm("runs.verify", self.test_run))

    def test_games_manage_allowed_for_mod(
        self,
    ) -> None:
        self.assertTrue(self.mod_user.has_perm("games.manage", self.game))

    def test_games_manage_denied_for_other_game(
        self,
    ) -> None:
        self.assertFalse(self.mod_user.has_perm("games.manage", self.other_game))

    def test_runs_delete_requires_superuser(
        self,
    ) -> None:
        self.assertFalse(self.mod_user.has_perm("runs.delete", self.test_run))
        self.assertTrue(self.super_user.has_perm("runs.delete", self.test_run))

    def test_runs_edit_own_requires_participation(
        self,
    ) -> None:
        p = Players.objects.create(
            id="capregp",
            name="capregp",
            url="https://speedrun.com/",
            countrycode=self.country,
            ex_stream=False,
            claim_status=Players.ClaimStatus.CLAIMED,
            user=self.regular_user,
        )
        self.assertFalse(
            self.regular_user.has_perm("runs.edit_own", self.test_run),
        )
        RunPlayers.objects.create(run=self.test_run, player=p, order=1)
        self.assertTrue(
            self.regular_user.has_perm("runs.edit_own", self.test_run),
        )

    def test_api_keys_create_own_requires_auth(
        self,
    ) -> None:
        self.assertFalse(has_perm("api_keys.create_own", AnonymousUser()))
        self.assertTrue(self.regular_user.has_perm("api_keys.create_own"))

    def test_users_admin_denied_for_regular_user(
        self,
    ) -> None:
        self.assertFalse(self.regular_user.has_perm("users.admin"))

    def test_users_admin_allowed_for_superuser(
        self,
    ) -> None:
        self.assertTrue(self.super_user.has_perm("users.admin"))
