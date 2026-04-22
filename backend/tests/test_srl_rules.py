from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from guides.models import Guides
from srl.models import (
    Categories,
    CountryCodes,
    Games,
    Platforms,
    Players,
    RunPlayers,
    Runs,
)
from srl.rules import (
    is_authenticated,
    is_game_moderator,
    is_guide_game_moderator,
    is_run_game_moderator,
    is_run_participant,
    is_superuser,
    owns_guide,
)

User = get_user_model()


class SrlRulesTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.country = CountryCodes.objects.create(id="usa", name="United States")

        cls.platform = Platforms.objects.create(
            id="pc",
            name="PC",
            slug="pc",
        )

        cls.game = Games.objects.create(
            id="game1",
            name="Test Game",
            slug="test-game",
            twitch="Test Game",
            release="2000-01-01",
            boxart="https://example.com/cover",
            defaulttime="realtime",
            idefaulttime="realtime",
            pointsmax=1000,
            ipointsmax=100,
        )

        cls.other_game = Games.objects.create(
            id="game2",
            name="Other Game",
            slug="other-game",
            twitch="Other Game",
            release="2001-01-01",
            boxart="https://example.com/other-cover",
            defaulttime="realtime",
            idefaulttime="realtime",
            pointsmax=1000,
            ipointsmax=100,
        )

        cls.category = Categories.objects.create(
            id="cat1",
            game=cls.game,
            name="Any%",
            slug="any",
            type="per-game",
            url="https://speedrun.com/test-game",
            archive=False,
        )

        cls.mod_user = User.objects.create_user(
            username="moduser",
            email="mod@example.com",
            password="testpass123",
        )
        cls.mod_player = Players.objects.create(
            id="modplyr1",
            name="ModPlayer",
            url="https://speedrun.com/",
            countrycode=cls.country,
            ex_stream=False,
            claim_status=Players.ClaimStatus.CLAIMED,
            user=cls.mod_user,
        )
        cls.game.moderators.add(cls.mod_player)

        cls.regular_user = User.objects.create_user(
            username="regularuser",
            email="regular@example.com",
            password="testpass123",
        )
        cls.regular_player = Players.objects.create(
            id="regplyr1",
            name="RegularPlayer",
            url="https://speedrun.com/",
            countrycode=cls.country,
            ex_stream=False,
            claim_status=Players.ClaimStatus.CLAIMED,
            user=cls.regular_user,
        )

        cls.super_user = User.objects.create_superuser(
            username="superuser",
            email="super@example.com",
            password="testpass123",
        )

        cls.unlinked_user = User.objects.create_user(
            username="unlinkeduser",
            email="unlinked@example.com",
            password="testpass123",
        )

        cls.test_run = Runs.objects.create(
            id="run001",
            runtype="main",
            game=cls.game,
            category=cls.category,
            place=1,
            url="https://speedrun.com/run001",
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
        RunPlayers.objects.create(
            run=cls.test_run,
            player=cls.regular_player,
            order=1,
        )

    def test_is_authenticated_with_authenticated_user(self) -> None:
        self.assertTrue(is_authenticated(self.regular_user))

    def test_is_authenticated_with_none(self) -> None:
        self.assertFalse(is_authenticated(None))

    def test_is_superuser_with_superuser(self) -> None:
        self.assertTrue(is_superuser(self.super_user))

    def test_is_superuser_with_regular_user(self) -> None:
        self.assertFalse(is_superuser(self.regular_user))

    def test_is_superuser_with_none(self) -> None:
        self.assertFalse(is_superuser(None))

    def test_is_game_moderator_true_when_player_is_mod(self) -> None:
        self.assertTrue(is_game_moderator(self.mod_user, self.game))

    def test_is_game_moderator_false_for_different_game(self) -> None:
        self.assertFalse(is_game_moderator(self.mod_user, self.other_game))

    def test_is_game_moderator_false_for_regular_user(self) -> None:
        self.assertFalse(is_game_moderator(self.regular_user, self.game))

    def test_is_game_moderator_false_without_player_link(self) -> None:
        self.assertFalse(is_game_moderator(self.unlinked_user, self.game))

    def test_is_game_moderator_false_for_anon(self) -> None:
        self.assertFalse(is_game_moderator(None, self.game))

    def test_is_game_moderator_false_when_game_is_none(self) -> None:
        self.assertFalse(is_game_moderator(self.mod_user, None))

    def test_is_run_participant_true_for_run_player(self) -> None:
        self.assertTrue(is_run_participant(self.regular_user, self.test_run))

    def test_is_run_participant_false_for_non_participant(self) -> None:
        self.assertFalse(is_run_participant(self.mod_user, self.test_run))

    def test_is_run_participant_false_without_player_link(self) -> None:
        self.assertFalse(is_run_participant(self.unlinked_user, self.test_run))

    def test_is_run_participant_false_for_anon(self) -> None:
        self.assertFalse(is_run_participant(None, self.test_run))

    def test_is_run_participant_false_when_run_is_none(self) -> None:
        self.assertFalse(is_run_participant(self.regular_user, None))

    def test_is_run_game_moderator_true_for_game_mod(self) -> None:
        self.assertTrue(is_run_game_moderator(self.mod_user, self.test_run))

    def test_is_run_game_moderator_false_for_non_mod(self) -> None:
        self.assertFalse(is_run_game_moderator(self.regular_user, self.test_run))

    def test_is_run_game_moderator_false_for_anon(self) -> None:
        self.assertFalse(is_run_game_moderator(None, self.test_run))

    def test_is_run_game_moderator_false_when_run_is_none(self) -> None:
        self.assertFalse(is_run_game_moderator(self.mod_user, None))

    def test_owns_guide_true_for_owner(self) -> None:
        guide = Guides.objects.create(
            title="My Guide",
            slug="my-guide",
            game=self.game,
            short_description="Test",
            content="Content",
            owner=self.regular_user,
        )
        self.assertTrue(owns_guide(self.regular_user, guide))

    def test_owns_guide_false_for_other_user(self) -> None:
        guide = Guides.objects.create(
            title="Their Guide",
            slug="their-guide",
            game=self.game,
            short_description="Test",
            content="Content",
            owner=self.mod_user,
        )
        self.assertFalse(owns_guide(self.regular_user, guide))

    def test_owns_guide_false_when_guide_has_no_owner(self) -> None:
        guide = Guides.objects.create(
            title="Orphan Guide",
            slug="orphan-guide",
            game=self.game,
            short_description="Test",
            content="Content",
            owner=None,
        )
        self.assertFalse(owns_guide(self.regular_user, guide))

    def test_owns_guide_false_for_anon(self) -> None:
        guide = Guides.objects.create(
            title="Anon Guide",
            slug="anon-guide",
            game=self.game,
            short_description="Test",
            content="Content",
            owner=self.regular_user,
        )
        self.assertFalse(owns_guide(None, guide))

    def test_is_guide_game_moderator_true_for_mod(self) -> None:
        guide = Guides.objects.create(
            title="Mod Guide",
            slug="mod-guide",
            game=self.game,
            short_description="Test",
            content="Content",
            owner=self.regular_user,
        )
        self.assertTrue(is_guide_game_moderator(self.mod_user, guide))

    def test_is_guide_game_moderator_false_for_other_game(self) -> None:
        guide = Guides.objects.create(
            title="Other-Game Guide",
            slug="other-game-guide",
            game=self.other_game,
            short_description="Test",
            content="Content",
            owner=self.regular_user,
        )
        self.assertFalse(is_guide_game_moderator(self.mod_user, guide))

    def test_is_guide_game_moderator_false_for_anon(self) -> None:
        guide = Guides.objects.create(
            title="Anon Mod Guide",
            slug="anon-mod-guide",
            game=self.game,
            short_description="Test",
            content="Content",
            owner=self.regular_user,
        )
        self.assertFalse(is_guide_game_moderator(None, guide))

    def test_is_guide_game_moderator_false_when_guide_is_none(self) -> None:
        self.assertFalse(is_guide_game_moderator(self.mod_user, None))
