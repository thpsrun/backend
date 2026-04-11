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


from django.contrib.auth import get_user_model
from django.test import Client
from srl.models import Players


class AuthMeTestBase(TestCase):

    @classmethod
    def setUpTestData(cls) -> None:
        cls.country = CountryCodes.objects.create(
            id="can",
            name="Canada",
        )
        User = get_user_model()
        cls.user = User.objects.create_user(  # type: ignore
            username="testplayer",
            email="testplayer@example.com",
            password="supersecret123",
        )
        cls.user.bio = "hello world"
        cls.user.short_bio = "hi"
        cls.user.gradient_1 = "#ff0000"
        cls.user.save()

        cls.player = Players.objects.create(
            id="testplayer01",
            name="TestPlayer",
            nickname="Tester",
            url="https://speedrun.com/user/TestPlayer",
            countrycode=cls.country,
            pronouns="they/them",
            twitch="https://twitch.tv/testplayer",
            youtube=None,
            twitter=None,
            bluesky=None,
            discord=None,
            ex_stream=False,
            claim_status=Players.ClaimStatus.CLAIMED,
            user=cls.user,
        )

    def setUp(self) -> None:
        self.client = Client()
        self.client.force_login(self.user)


class AuthMeReadTest(AuthMeTestBase):

    def test_get_me_returns_nested_shape(self) -> None:
        response = self.client.get("/api/v1/auth/me")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["player_id"], "testplayer01")
        self.assertEqual(data["claim_status"], Players.ClaimStatus.CLAIMED)
        self.assertIn("joined", data)

        self.assertIn("player", data)
        player = data["player"]
        self.assertEqual(player["username"], "testplayer")
        self.assertEqual(player["name"], "TestPlayer")
        self.assertEqual(player["nickname"], "Tester")
        self.assertEqual(player["pronouns"], "they/them")
        self.assertEqual(player["is_superuser"], False)
        self.assertEqual(player["ex_stream"], False)

        self.assertIsInstance(player["country"], dict)
        self.assertEqual(player["country"]["id"], "can")
        self.assertEqual(player["country"]["name"], "Canada")
        self.assertIn("flag", player["country"])

        self.assertIn("socials", data)
        socials = data["socials"]
        self.assertEqual(socials["twitch"], "https://twitch.tv/testplayer")
        self.assertIsNone(socials["youtube"])
        self.assertIsNone(socials["discord"])
        self.assertIn("therun_gg", socials)

        self.assertIn("customizations", data)
        custom = data["customizations"]
        self.assertEqual(custom["bio"], "hello world")
        self.assertEqual(custom["short_bio"], "hi")
        self.assertEqual(custom["gradient_1"], "#ff0000")
        self.assertIsNone(custom["gradient_2"])
        self.assertIsNone(custom["gradient_3"])

        self.assertIn("moderation", data)
        moderation = data["moderation"]
        self.assertEqual(moderation["has_src_key"], False)
        self.assertEqual(moderation["moderated_games"], [])

    def test_get_me_unauthenticated(self) -> None:
        self.client.logout()
        response = self.client.get("/api/v1/auth/me")
        self.assertEqual(response.status_code, 401)

    def test_get_me_null_country(self) -> None:
        self.player.countrycode = None
        self.player.save(update_fields=["countrycode"])
        response = self.client.get("/api/v1/auth/me")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["player"]["country"])


class AuthMeUpdateTest(AuthMeTestBase):

    def test_patch_player_group(self) -> None:
        response = self.client.patch(
            "/api/v1/auth/me",
            data={"player": {"nickname": "NewNick", "pronouns": "she/her"}},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["player"]["nickname"], "NewNick")
        self.assertEqual(data["player"]["pronouns"], "she/her")
        self.assertEqual(data["player"]["name"], "TestPlayer")
        self.assertEqual(data["socials"]["twitch"], "https://twitch.tv/testplayer")
        self.assertEqual(data["customizations"]["bio"], "hello world")

    def test_patch_socials_group_with_therun_gg(self) -> None:
        response = self.client.patch(
            "/api/v1/auth/me",
            data={
                "socials": {
                    "twitch": "https://twitch.tv/newhandle",
                    "therun_gg": "newhandle",
                },
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["socials"]["twitch"], "https://twitch.tv/newhandle")
        self.assertEqual(data["socials"]["therun_gg"], "newhandle")

    def test_patch_explicit_null_clears_field(self) -> None:
        response = self.client.patch(
            "/api/v1/auth/me",
            data={"player": {"nickname": None}},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["player"]["nickname"])

    def test_patch_omitted_group_untouched(self) -> None:
        response = self.client.patch(
            "/api/v1/auth/me",
            data={"customizations": {"bio": "changed"}},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["customizations"]["bio"], "changed")
        self.assertEqual(data["player"]["nickname"], "Tester")
        self.assertEqual(data["socials"]["twitch"], "https://twitch.tv/testplayer")

    def test_patch_invalid_country_returns_400(self) -> None:
        response = self.client.patch(
            "/api/v1/auth/me",
            data={"player": {"country": "zzz"}},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("country", response.json()["error"].lower())

    def test_patch_invalid_gradient_hex_returns_422(self) -> None:
        response = self.client.patch(
            "/api/v1/auth/me",
            data={"customizations": {"gradient_1": "not-a-hex"}},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 422)

    def test_patch_gradient_2_without_gradient_1_returns_400(self) -> None:
        self.user.gradient_1 = None
        self.user.save(update_fields=["gradient_1"])
        response = self.client.patch(
            "/api/v1/auth/me",
            data={"customizations": {"gradient_2": "#00ff00"}},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("gradient_1", response.json()["error"])

    def test_patch_discord_field_not_accepted(self) -> None:
        response = self.client.patch(
            "/api/v1/auth/me",
            data={"socials": {"discord": "something"}},
            content_type="application/json",
        )
        self.player.refresh_from_db()
        self.assertIsNone(self.player.discord)
