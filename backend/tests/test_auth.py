from api.models import RoleAPIKey
from django.test import TestCase
from srl.models import CountryCodes, Games, Platforms


class AuthTestBase(TestCase):

    @classmethod
    def setUpTestData(cls) -> None:
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
            boxart="https://speedrun.com/game1/cover",
            defaulttime="realtime",
            idefaulttime="realtime",
            pointsmax=1000,
            ipointsmax=100,
        )
        cls.game.platforms.add("pc")

        cls.country = CountryCodes.objects.create(id="usa", name="United States")

    def setUp(self) -> None:
        self.key_obj, self.api_key = RoleAPIKey.objects.create_key(  # type: ignore
            name="Test Admin Key",
            role="admin",
            description="Temporary key for automated testing",
        )
