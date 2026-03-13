import datetime

from api.models import RoleAPIKey
from api.v1.routers.resources.categories import router as categories_router
from api.v1.routers.resources.games import router as games_router
from api.v1.routers.resources.levels import router as levels_router
from api.v1.routers.resources.platforms import router as platforms_router
from api.v1.routers.resources.players import router as players_router
from api.v1.routers.resources.runs import router as runs_router
from api.v1.routers.resources.streams import router as streams_router
from api.v1.routers.resources.variables import router as variables_router
from django.test import Client, TestCase
from django.utils import timezone
from ninja.testing import TestClient
from srl.models import (
    Awards,
    Categories,
    CountryCodes,
    Games,
    Levels,
    NowStreaming,
    Platforms,
    Players,
    RunPlayers,
    Runs,
    RunVariableValues,
    Series,
    Variables,
    VariableValues,
)


class HomepageTestCase(TestCase):
    def setUp(self) -> None:
        self.client = Client()

    def test_homepage_returns_404(self) -> None:
        """Homepage route is not served by Django (React frontend handles it)."""
        response = self.client.get("/")
        # Django backend doesn't serve a homepage - the React frontend does
        self.assertEqual(response.status_code, 404)


class ModelTestCase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.series = Series.objects.create(
            id="123abc",
            name="Tony Hank",
            url="https://speedrun.com",
        )

        cls.platform = Platforms.objects.create(
            id="xbox",
            name="Xbox 720",
            slug="xbox-720",
        )

        cls.games = Games.objects.create(
            id="asdef",
            name="Tony Hank's Pro Skateboarding 1",
            slug="thps1",
            twitch="Tony Hank's Pro Skateboarding 2",
            release="1999-12-31",
            boxart="https://speedrun.com/",
            defaulttime="realtime_noloads",
            idefaulttime="ingame",
            pointsmax=9999,
            ipointsmax=1000,
        )
        cls.games.platforms.add(cls.platform)

        cls.categories = Categories.objects.create(
            id="category",
            game=cls.games,
            name="Test Category 1",
            slug="test-category-1",
            type="per-game",
            url="https://speedrun.com/sm64",
            archive=False,
        )

        cls.levels = Levels.objects.create(
            id="level",
            game=cls.games,
            name="Test Level 1",
            slug="test-level-1",
            url="https://speedrun.com/sm64",
        )

        cls.variables = Variables.objects.create(
            id="var1",
            name="Variable Lariable",
            slug="variable-lariable",
            game=cls.games,
            cat=cls.categories,
            scope="global",
            archive=False,
        )

        cls.values = VariableValues.objects.create(
            var=cls.variables,
            name="Valueeeeeeeeeee",
            slug="valueeeeeeeeeee",
            value="val1",
            archive=False,
        )

        cls.awards = Awards.objects.create(
            id=1,
            name="Best in the World",
            description="Simply the best",
        )

        cls.countrycodes = CountryCodes.objects.create(id="usa", name="United States")

        cls.player1 = Players.objects.create(
            id="player1",
            name="Bob",
            nickname="Bobby B",
            url="https://speedrun.com/",
            countrycode=cls.countrycodes,
            pfp="https://google.com/",
            pronouns="He/Him/Them/They",
            twitch="Twitch",
            youtube="Youtube",
            twitter="Twitter",
            bluesky="Bluesky",
            ex_stream=True,
        )
        cls.player1.awards.add(cls.awards)

        cls.player2 = Players.objects.create(
            id="player2",
            name="Sam",
            nickname="Sammy",
            url="https://speedrun.com/",
            countrycode=cls.countrycodes,
            pfp="https://google.com/",
            pronouns="He/Him/Them/They",
            twitch="Twitch",
            youtube="Youtube",
            twitter="Twitter",
            bluesky="Bluesky",
            ex_stream=True,
        )
        cls.player2.awards.add(cls.awards)

        cls.runs = Runs.objects.create(
            id="run123",
            runtype="il",
            game=cls.games,
            category=cls.categories,
            level=cls.levels,
            place=666,
            url="https://speedrun.com/",
            video="https://speedrun.com/",
            date=timezone.now(),
            v_date=timezone.now(),
            time="0m 00s",
            time_secs=0.0,
            timenl="0m 00s",
            timenl_secs=0.0,
            timeigt="5m 33s",
            timeigt_secs=999.92,
            points=1000,
            platform=cls.platform,
            emulated=True,
            vid_status="verified",
            approver=cls.player1,
            obsolete=True,
            arch_video="https://speedrun.com/",
            description="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        )

        # Add players to run using the through model
        RunPlayers.objects.create(
            run=cls.runs,
            player=cls.player2,
            order=1,
        )

        cls.runvariablevalues = RunVariableValues.objects.create(
            id=1,
            run=cls.runs,
            variable=cls.variables,
            value=cls.values,
        )

        cls.nowstreaming = NowStreaming.objects.create(
            streamer=cls.player2,
            game=cls.games,
            title="Heckin good",
            offline_ct=9,
            stream_time=timezone.now(),
        )

    def test_series(self) -> None:
        self.assertTrue(Series.objects.filter(id="123abc").exists())

    def test_platforms(self) -> None:
        self.assertTrue(Platforms.objects.filter(id="xbox").exists())

    def test_games(self) -> None:
        self.assertTrue(Games.objects.filter(id="asdef").exists())

    def test_categories(self) -> None:
        self.assertTrue(Categories.objects.filter(id="category").exists())

    def test_levels(self) -> None:
        self.assertTrue(Levels.objects.filter(id="level").exists())

    def test_variables(self) -> None:
        self.assertTrue(Variables.objects.filter(id="var1").exists())

    def test_variablevalues(self) -> None:
        self.assertTrue(VariableValues.objects.filter(value="val1").exists())

    def test_players(self) -> None:
        self.assertTrue(Players.objects.filter(id="player1").exists())
        self.assertTrue(Players.objects.filter(id="player2").exists())

    def test_runs(self) -> None:
        self.assertTrue(Runs.objects.filter(id="run123").exists())
        self.assertTrue(RunVariableValues.objects.filter(id=1).exists())

    def test_streaming(self) -> None:
        self.assertTrue(NowStreaming.objects.all().exists())


class APIGamesTestCase(TestCase):
    """Tests for the Games API endpoints."""

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

    def setUp(self) -> None:
        self.client = TestClient(games_router)

    def test_get_all_games(self) -> None:
        """Test GET /games/all endpoint."""
        response = self.client.get("/all")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], "game1")
        self.assertEqual(data[0]["name"], "Test Game")

    def test_get_game_by_id(self) -> None:
        """Test GET /games/{id} endpoint."""
        response = self.client.get("/game1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "game1")
        self.assertEqual(data["name"], "Test Game")
        self.assertEqual(data["slug"], "test-game")

    def test_get_game_by_slug(self) -> None:
        """Test GET /games/{slug} endpoint."""
        response = self.client.get("/test-game")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "game1")

    def test_get_game_not_found(self) -> None:
        """Test GET /games/{id} returns 404 for non-existent game."""
        response = self.client.get("/nonexistent")
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data["error"], "Game does not exist")


class APICategoriesTestCase(TestCase):
    """Tests for the Categories API endpoints."""

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

        cls.category = Categories.objects.create(
            id="cat1",
            game=cls.game,
            name="Any%",
            slug="any",
            type="per-game",
            url="https://speedrun.com/test-game#any",
            archive=False,
        )

    def setUp(self) -> None:
        self.client = TestClient(categories_router)

    def test_get_all_categories_requires_game(self) -> None:
        """Test GET /categories/all requires game parameter."""
        response = self.client.get("/all")
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "Please provide the game's unique ID or slug.")

    def test_get_all_categories_with_game(self) -> None:
        """Test GET /categories/all?game=game1 endpoint."""
        response = self.client.get("/all?game=game1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], "cat1")
        self.assertEqual(data[0]["name"], "Any%")

    def test_get_category_by_id(self) -> None:
        """Test GET /categories/{id} endpoint."""
        response = self.client.get("/cat1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "cat1")
        self.assertEqual(data["name"], "Any%")

    def test_get_category_not_found(self) -> None:
        """Test GET /categories/{id} returns 404 for non-existent category."""
        response = self.client.get("/nonexistent")
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data["error"], "Category ID Doesn't Exist")


class APILevelsTestCase(TestCase):
    """Tests for the Levels API endpoints."""

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

        cls.level = Levels.objects.create(
            id="level1",
            game=cls.game,
            name="Warehouse",
            slug="warehouse",
            url="https://speedrun.com/test-game/Warehouse",
        )

    def setUp(self) -> None:
        self.client = TestClient(levels_router)

    def test_get_all_levels(self) -> None:
        """Test GET /levels/all endpoint."""
        response = self.client.get("/all")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], "level1")
        self.assertEqual(data[0]["name"], "Warehouse")

    def test_get_level_by_id(self) -> None:
        """Test GET /levels/{id} endpoint."""
        response = self.client.get("/level1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "level1")
        self.assertEqual(data["name"], "Warehouse")

    def test_get_level_not_found(self) -> None:
        """Test GET /levels/{id} returns 404 for non-existent level."""
        response = self.client.get("/nonexistent")
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data["error"], "Level ID does not exist")


class APIPlatformsTestCase(TestCase):
    """Tests for the Platforms API endpoints."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.platform = Platforms.objects.create(
            id="pc",
            name="PC",
            slug="pc",
        )

    def setUp(self) -> None:
        self.client = TestClient(platforms_router)

    def test_get_all_platforms(self) -> None:
        """Test GET /platforms/all endpoint."""
        response = self.client.get("/all")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], "pc")
        self.assertEqual(data[0]["name"], "PC")

    def test_get_platform_by_id(self) -> None:
        """Test GET /platforms/{id} endpoint."""
        response = self.client.get("/pc")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "pc")
        self.assertEqual(data["name"], "PC")

    def test_get_platform_not_found(self) -> None:
        """Test GET /platforms/{id} returns 404 for non-existent platform."""
        response = self.client.get("/nonexistent")
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data["error"], "Platform ID does not exist")


class APIPlayersTestCase(TestCase):
    """Tests for the Players API endpoints."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.country = CountryCodes.objects.create(id="usa", name="United States")
        cls.player = Players.objects.create(
            id="player1",
            name="TestPlayer",
            nickname="Tester",
            url="https://speedrun.com/user/TestPlayer",
            countrycode=cls.country,
            pronouns="They/Them",
            twitch="https://twitch.tv/testplayer",
            youtube="https://youtube.com/testplayer",
            twitter="https://twitter.com/testplayer",
            bluesky="https://bsky.app/testplayer",
            ex_stream=False,
        )

    def setUp(self) -> None:
        self.client = TestClient(players_router)

    def test_get_player_by_id(self) -> None:
        """Test GET /players/{id} endpoint."""
        response = self.client.get("/player1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "player1")
        self.assertEqual(data["name"], "TestPlayer")
        self.assertEqual(data["nickname"], "Tester")

    def test_get_player_by_name(self) -> None:
        """Test GET /players/{name} endpoint (lookup by name)."""
        response = self.client.get("/TestPlayer")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "player1")

    def test_get_player_by_nickname(self) -> None:
        """Test GET /players/{nickname} endpoint (lookup by nickname)."""
        response = self.client.get("/Tester")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "player1")

    def test_get_player_not_found(self) -> None:
        """Test GET /players/{id} returns 404 for non-existent player."""
        response = self.client.get("/nonexistent")
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data["error"], "Player ID does not exist")


class APIVariablesTestCase(TestCase):
    """Tests for the Variables API endpoints."""

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

        cls.category = Categories.objects.create(
            id="cat1",
            game=cls.game,
            name="Any%",
            slug="any",
            type="per-game",
            url="https://speedrun.com/test-game#any",
            archive=False,
        )

        cls.variable = Variables.objects.create(
            id="var1",
            name="Difficulty",
            slug="difficulty",
            game=cls.game,
            cat=cls.category,
            scope="full-game",
            archive=False,
        )

        cls.value = VariableValues.objects.create(
            var=cls.variable,
            name="Normal",
            slug="normal",
            value="val1",
            archive=False,
        )

    def setUp(self) -> None:
        self.client = TestClient(variables_router)

    def test_get_all_variables(self) -> None:
        """Test GET /variables/all endpoint."""
        response = self.client.get("/all")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], "var1")
        self.assertEqual(data[0]["name"], "Difficulty")

    def test_get_variable_by_id(self) -> None:
        """Test GET /variables/{id} endpoint."""
        response = self.client.get("/var1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "var1")
        self.assertEqual(data["name"], "Difficulty")
        # Variable values should be embedded
        self.assertIsNotNone(data.get("values"))

    def test_get_variable_not_found(self) -> None:
        """Test GET /variables/{id} returns 404 for non-existent variable."""
        response = self.client.get("/nonexistent")
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data["error"], "Variable ID does not exist")


class APIRunsTestCase(TestCase):
    """Tests for the Runs API endpoints."""

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

        cls.category = Categories.objects.create(
            id="cat1",
            game=cls.game,
            name="Any%",
            slug="any",
            type="per-game",
            url="https://speedrun.com/test-game#any",
            archive=False,
        )

        cls.country = CountryCodes.objects.create(id="usa", name="United States")
        cls.player = Players.objects.create(
            id="player1",
            name="TestPlayer",
            nickname="Tester",
            url="https://speedrun.com/user/TestPlayer",
            countrycode=cls.country,
        )

        cls.test_run = Runs.objects.create(
            id="run1",
            runtype="main",
            game=cls.game,
            category=cls.category,
            place=1,
            url="https://speedrun.com/test-game/run/run1",
            video="https://youtube.com/watch?v=abc123",
            date=timezone.make_aware(datetime.datetime(2024, 1, 1)),
            v_date=timezone.make_aware(datetime.datetime(2024, 1, 2)),
            time="5m 30s",
            time_secs=330.0,
            vid_status="verified",
        )

        # Add player to run using through model
        RunPlayers.objects.create(
            run=cls.test_run,
            player=cls.player,
            order=1,
        )

    def setUp(self) -> None:
        self.client = TestClient(runs_router)

    def test_get_all_runs(self) -> None:
        """Test GET /runs/all endpoint."""
        response = self.client.get("/all")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], "run1")

    def test_get_all_runs_with_game_filter(self) -> None:
        """Test GET /runs/all?game_id=game1 endpoint."""
        response = self.client.get("/all?game_id=game1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], "run1")

    def test_get_run_by_id(self) -> None:
        """Test GET /runs/{id} endpoint."""
        response = self.client.get("/run1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "run1")
        self.assertEqual(data["time"], "5m 30s")
        self.assertEqual(data["place"], 1)

    def test_get_run_with_game_embed(self) -> None:
        """Test GET /runs/{id}?embed=game endpoint."""
        response = self.client.get("/run1?embed=game")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "run1")
        self.assertIsNotNone(data.get("game"))
        self.assertEqual(data["game"]["id"], "game1")
        self.assertEqual(data["game"]["name"], "Test Game")

    def test_get_run_includes_players(self) -> None:
        """Test GET /runs/{id} always includes the players array."""
        response = self.client.get("/run1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "run1")
        self.assertIsInstance(data["players"], list)
        self.assertEqual(len(data["players"]), 1)
        self.assertEqual(data["players"][0]["id"], "player1")

    def test_get_run_not_found(self) -> None:
        """Test GET /runs/{id} returns 404 for non-existent run."""
        response = self.client.get("/nonexistent")
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data["error"], "Run ID does not exist")

    def test_get_run_invalid_embed(self) -> None:
        """Test GET /runs/{id}?embed=invalid returns error for invalid embed."""
        response = self.client.get("/run1?embed=invalid")
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("Invalid embed", data["error"])


class APIStreamsTestCase(TestCase):
    """Tests for the Streams API endpoints."""

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

        cls.player = Players.objects.create(
            id="player1",
            name="TestPlayer",
            nickname="Tester",
            url="https://speedrun.com/user/TestPlayer",
            twitch="https://twitch.tv/testplayer",
        )

        cls.stream = NowStreaming.objects.create(
            streamer=cls.player,
            game=cls.game,
            title="Testing my speedruns!",
            offline_ct=0,
            stream_time=timezone.now(),
        )

    def setUp(self) -> None:
        self.client = TestClient(streams_router)

    def test_get_live_streams(self) -> None:
        """Test GET /streams/live endpoint.

        Note: The /live endpoint currently returns mock data for demonstration
        purposes, not data from the database. This test validates the mock
        data structure is returned correctly.
        """
        response = self.client.get("/live")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        # The endpoint returns mock data, so check that structure is correct
        self.assertGreater(len(data), 0, "Expected at least one mock stream")
        first_stream = data[0]
        self.assertIsNotNone(first_stream.get("title"))
        self.assertIsNotNone(first_stream.get("player"))
        self.assertIsNotNone(first_stream.get("game"))


# =============================================================================
# POST, PUT, DELETE Endpoint Tests (Require API Key Authentication)
# =============================================================================


class AuthenticatedAPITestCase(TestCase):
    """Base class for tests requiring API key authentication.

    Creates a temporary admin API key for testing POST/PUT/DELETE endpoints.
    The key is automatically cleaned up after each test via Django's test
    transaction rollback.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        # Create base test data that all authenticated tests need
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
        # Create a temporary admin API key for each test
        # Using create_key() returns (key_object, actual_key_string)
        self.api_key_obj, self.api_key = RoleAPIKey.objects.create_key(
            name="Test Admin Key",
            role="admin",
            description="Temporary key for automated testing",
        )


class APIGamesWriteTestCase(AuthenticatedAPITestCase):
    """Tests for Games POST/PUT/DELETE endpoints."""

    def setUp(self) -> None:
        super().setUp()
        self.client = TestClient(games_router)

    def test_create_game(self) -> None:
        """Test POST /games/ endpoint creates a new game."""
        response = self.client.post(
            "/",
            json={
                "name": "New Test Game",
                "slug": "new-test-game",
                "twitch": "New Test Game",
                "release": "2024-06-15",
                "boxart": "https://example.com/boxart.png",
                "defaulttime": "realtime",
                "idefaulttime": "realtime",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "New Test Game")
        self.assertEqual(data["slug"], "new-test-game")
        # ID should be auto-generated
        self.assertIsNotNone(data.get("id"))
        self.assertEqual(len(data["id"]), 8)

    def test_create_game_with_custom_id(self) -> None:
        """Test POST /games/ with custom ID."""
        response = self.client.post(
            "/",
            json={
                "id": "customid",
                "name": "Custom ID Game",
                "slug": "custom-id-game",
                "twitch": "Custom ID Game",
                "release": "2024-06-15",
                "boxart": "https://example.com/boxart.png",
                "defaulttime": "realtime",
                "idefaulttime": "realtime",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "customid")

    def test_create_game_duplicate_id_fails(self) -> None:
        """Test POST /games/ with existing ID returns error."""
        response = self.client.post(
            "/",
            json={
                "id": "game1",  # Already exists from setUpTestData
                "name": "Duplicate ID Game",
                "slug": "dup-id-game",
                "twitch": "Duplicate ID Game",
                "release": "2024-06-15",
                "boxart": "https://example.com/boxart.png",
                "defaulttime": "realtime",
                "idefaulttime": "realtime",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "ID Already Exists")

    def test_create_game_with_invalid_auth_fails(self) -> None:
        full_client = Client()
        response = full_client.post(
            "/api/v1/games/",
            data={
                "name": "Unauthorized Game",
                "slug": "unauth-game",
                "twitch": "Unauthorized Game",
                "release": "2024-06-15",
                "boxart": "https://example.com/boxart.png",
                "defaulttime": "realtime",
                "idefaulttime": "realtime",
            },
            content_type="application/json",
            HTTP_X_API_KEY="invalid.key.here",
        )
        # The endpoint should reject invalid API keys with 401 Unauthorized
        self.assertEqual(response.status_code, 401)
        # Verify the game was NOT created
        self.assertFalse(Games.objects.filter(name="Unauthorized Game").exists())

    def test_update_game(self) -> None:
        """Test PUT /games/{id} endpoint updates a game."""
        response = self.client.put(
            "/game1",
            json={
                "name": "Updated Game Name",
                "slug": "updated-game",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "game1")
        self.assertEqual(data["name"], "Updated Game Name")
        self.assertEqual(data["slug"], "updated-game")

    def test_update_nonexistent_game_fails(self) -> None:
        """Test PUT /games/{id} with non-existent ID returns 404."""
        response = self.client.put(
            "/nonexistent",
            json={"name": "Updated Name", "slug": "updated"},
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 404)

    def test_delete_game(self) -> None:
        """Test DELETE /games/{id} endpoint deletes a game."""
        # First create a game to delete
        Games.objects.create(
            id="todelete",
            name="To Delete",
            slug="to-delete",
            twitch="To Delete",
            release="2024-01-01",
            boxart="https://example.com/boxart.png",
            defaulttime="realtime",
            idefaulttime="realtime",
        )

        response = self.client.delete(
            "/todelete",
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("deleted successfully", data["message"])

        # Verify game is deleted
        self.assertFalse(Games.objects.filter(id="todelete").exists())

    def test_delete_nonexistent_game_fails(self) -> None:
        """Test DELETE /games/{id} with non-existent ID returns 404."""
        response = self.client.delete(
            "/nonexistent",
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 404)


class APIPlatformsWriteTestCase(AuthenticatedAPITestCase):
    """Tests for Platforms POST/PUT/DELETE endpoints."""

    def setUp(self) -> None:
        super().setUp()
        self.client = TestClient(platforms_router)

    def test_create_platform(self) -> None:
        """Test POST /platforms/ endpoint creates a new platform."""
        response = self.client.post(
            "/",
            json={
                "name": "PlayStation 5",
                "slug": "ps5",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "PlayStation 5")
        self.assertEqual(data["slug"], "ps5")
        # ID should be auto-generated
        self.assertIsNotNone(data.get("id"))
        self.assertEqual(len(data["id"]), 8)

    def test_create_platform_with_custom_id(self) -> None:
        """Test POST /platforms/ with custom ID."""
        response = self.client.post(
            "/",
            json={
                "id": "xbox360",
                "name": "Xbox 360",
                "slug": "xbox-360",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "xbox360")

    def test_create_platform_duplicate_id_fails(self) -> None:
        """Test POST /platforms/ with existing ID returns error."""
        response = self.client.post(
            "/",
            json={
                "id": "pc",  # Already exists
                "name": "Another PC",
                "slug": "another-pc",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "ID Already Exists")

    def test_update_platform(self) -> None:
        """Test PUT /platforms/{id} endpoint updates a platform."""
        response = self.client.put(
            "/pc",
            json={"name": "Personal Computer"},
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "pc")
        self.assertEqual(data["name"], "Personal Computer")

    def test_delete_platform(self) -> None:
        """Test DELETE /platforms/{id} endpoint deletes a platform."""
        Platforms.objects.create(id="todelete", name="To Delete", slug="to-delete")

        response = self.client.delete(
            "/todelete",
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("deleted successfully", data["message"])
        self.assertFalse(Platforms.objects.filter(id="todelete").exists())


class APIPlayersWriteTestCase(AuthenticatedAPITestCase):
    """Tests for Players POST/PUT/DELETE endpoints."""

    def setUp(self) -> None:
        super().setUp()
        self.client = TestClient(players_router)

    def test_create_player(self) -> None:
        """Test POST /players/ endpoint creates a new player."""
        response = self.client.post(
            "/",
            json={
                "name": "NewPlayer",
                "url": "https://speedrun.com/user/NewPlayer",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "NewPlayer")
        # ID should be auto-generated
        self.assertIsNotNone(data.get("id"))
        self.assertEqual(len(data["id"]), 8)

    def test_create_player_with_custom_id(self) -> None:
        """Test POST /players/ with custom ID."""
        response = self.client.post(
            "/",
            json={
                "id": "custom01",
                "name": "CustomPlayer",
                "url": "https://speedrun.com/user/CustomPlayer",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "custom01")

    def test_create_player_with_country(self) -> None:
        """Test POST /players/ with country code."""
        response = self.client.post(
            "/",
            json={
                "name": "PlayerWithCountry",
                "url": "https://speedrun.com/user/PlayerWithCountry",
                "country_id": "usa",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "PlayerWithCountry")
        # PlayerSchema doesn't expose country_id directly - country is an embed field
        # Verify the player was created with the country by checking the DB
        player = Players.objects.get(name="PlayerWithCountry")
        self.assertEqual(player.countrycode.id, "usa")

    def test_create_player_duplicate_id_fails(self) -> None:
        """Test POST /players/ with existing ID returns error."""
        # First create a player
        Players.objects.create(
            id="existing",
            name="Existing",
            url="https://speedrun.com/user/Existing",
        )

        response = self.client.post(
            "/",
            json={
                "id": "existing",
                "name": "Another",
                "url": "https://speedrun.com/user/Another",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "ID Already Exists")

    def test_update_player(self) -> None:
        """Test PUT /players/{id} endpoint updates a player."""
        Players.objects.create(
            id="toupdate",
            name="ToUpdate",
            url="https://speedrun.com/user/ToUpdate",
        )

        response = self.client.put(
            "/toupdate",
            json={
                "nickname": "UpdatedNick",
                "pronouns": "They/Them",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "toupdate")
        self.assertEqual(data["nickname"], "UpdatedNick")
        self.assertEqual(data["pronouns"], "They/Them")

    def test_delete_player(self) -> None:
        """Test DELETE /players/{id} endpoint deletes a player."""
        Players.objects.create(
            id="todelete",
            name="ToDelete",
            url="https://speedrun.com/user/ToDelete",
        )

        response = self.client.delete(
            "/todelete",
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("deleted successfully", data["message"])
        self.assertFalse(Players.objects.filter(id="todelete").exists())


class APICategoriesWriteTestCase(AuthenticatedAPITestCase):
    """Tests for Categories POST/PUT/DELETE endpoints."""

    def setUp(self) -> None:
        super().setUp()
        self.client = TestClient(categories_router)

    def test_create_category(self) -> None:
        """Test POST /categories/ endpoint creates a new category."""
        response = self.client.post(
            "/",
            json={
                "game_id": "game1",
                "name": "100%",
                "slug": "100-percent",
                "type": "per-game",
                "url": "https://speedrun.com/test-game#100",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "100%")
        self.assertEqual(data["slug"], "100-percent")
        # ID should be auto-generated
        self.assertIsNotNone(data.get("id"))
        self.assertEqual(len(data["id"]), 8)

    def test_create_category_with_custom_id(self) -> None:
        """Test POST /categories/ with custom ID."""
        response = self.client.post(
            "/",
            json={
                "id": "anyper",
                "game_id": "game1",
                "name": "Any%",
                "slug": "any-percent",
                "type": "per-game",
                "url": "https://speedrun.com/test-game#any",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "anyper")

    def test_create_category_nonexistent_game_fails(self) -> None:
        """Test POST /categories/ with non-existent game returns 404."""
        response = self.client.post(
            "/",
            json={
                "game_id": "nonexistent",
                "name": "Any%",
                "slug": "any",
                "type": "per-game",
                "url": "https://speedrun.com/test#any",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 404)

    def test_update_category(self) -> None:
        """Test PUT /categories/{id} endpoint updates a category."""
        Categories.objects.create(
            id="toupdate",
            game=self.game,
            name="ToUpdate",
            slug="to-update",
            type="per-game",
            url="https://speedrun.com/test#toupdate",
        )

        response = self.client.put(
            "/toupdate",
            json={"name": "Updated Category"},
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "toupdate")
        self.assertEqual(data["name"], "Updated Category")

    def test_delete_category(self) -> None:
        """Test DELETE /categories/{id} endpoint deletes a category."""
        Categories.objects.create(
            id="todelete",
            game=self.game,
            name="ToDelete",
            slug="to-delete",
            type="per-game",
            url="https://speedrun.com/test#todelete",
        )

        response = self.client.delete(
            "/todelete",
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("deleted successfully", data["message"])
        self.assertFalse(Categories.objects.filter(id="todelete").exists())


class APILevelsWriteTestCase(AuthenticatedAPITestCase):
    """Tests for Levels POST/PUT/DELETE endpoints."""

    def setUp(self) -> None:
        super().setUp()
        self.client = TestClient(levels_router)

    def test_create_level(self) -> None:
        """Test POST /levels/ endpoint creates a new level."""
        response = self.client.post(
            "/",
            json={
                "game_id": "game1",
                "name": "School",
                "slug": "school",
                "url": "https://speedrun.com/test-game/School",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "School")
        # ID should be auto-generated
        self.assertIsNotNone(data.get("id"))
        self.assertEqual(len(data["id"]), 8)

    def test_create_level_with_custom_id(self) -> None:
        """Test POST /levels/ with custom ID."""
        response = self.client.post(
            "/",
            json={
                "id": "lvl001",
                "game_id": "game1",
                "name": "Warehouse",
                "slug": "warehouse",
                "url": "https://speedrun.com/test-game/Warehouse",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "lvl001")

    def test_create_level_nonexistent_game_fails(self) -> None:
        """Test POST /levels/ with non-existent game returns 404."""
        response = self.client.post(
            "/",
            json={
                "game_id": "nonexistent",
                "name": "Level",
                "slug": "level",
                "url": "https://speedrun.com/test/Level",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 404)

    def test_update_level(self) -> None:
        """Test PUT /levels/{id} endpoint updates a level."""
        Levels.objects.create(
            id="toupdate",
            game=self.game,
            name="ToUpdate",
            slug="to-update",
            url="https://speedrun.com/test/ToUpdate",
        )

        response = self.client.put(
            "/toupdate",
            json={"name": "Updated Level"},
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "toupdate")
        self.assertEqual(data["name"], "Updated Level")

    def test_delete_level(self) -> None:
        """Test DELETE /levels/{id} endpoint deletes a level."""
        Levels.objects.create(
            id="todelete",
            game=self.game,
            name="ToDelete",
            slug="to-delete",
            url="https://speedrun.com/test/ToDelete",
        )

        response = self.client.delete(
            "/todelete",
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("deleted successfully", data["message"])
        self.assertFalse(Levels.objects.filter(id="todelete").exists())


class APIVariablesWriteTestCase(AuthenticatedAPITestCase):
    """Tests for Variables POST/PUT/DELETE endpoints."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.category = Categories.objects.create(
            id="cat1",
            game=cls.game,
            name="Any%",
            slug="any",
            type="per-game",
            url="https://speedrun.com/test-game#any",
        )

    def setUp(self) -> None:
        super().setUp()
        self.client = TestClient(variables_router)

    def test_create_variable(self) -> None:
        """Test POST /variables/ endpoint creates a new variable."""
        response = self.client.post(
            "/",
            json={
                "game_id": "game1",
                "name": "Difficulty",
                "slug": "difficulty",
                "scope": "full-game",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "Difficulty")
        # ID should be auto-generated
        self.assertIsNotNone(data.get("id"))
        self.assertEqual(len(data["id"]), 8)

    def test_create_variable_with_custom_id(self) -> None:
        """Test POST /variables/ with custom ID."""
        response = self.client.post(
            "/",
            json={
                "id": "var001",
                "game_id": "game1",
                "name": "Version",
                "slug": "version",
                "scope": "full-game",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "var001")

    def test_create_variable_with_category(self) -> None:
        """Test POST /variables/ with category scope."""
        response = self.client.post(
            "/",
            json={
                "game_id": "game1",
                "category_id": "cat1",
                "name": "Subcategory",
                "slug": "subcategory",
                "scope": "full-game",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "Subcategory")
        # VariableSchema doesn't expose cat_id directly - verify in DB
        variable = Variables.objects.get(name="Subcategory")
        self.assertEqual(variable.cat.id, "cat1")

    def test_update_variable(self) -> None:
        """Test PUT /variables/{id} endpoint updates a variable."""
        Variables.objects.create(
            id="toupdate",
            game=self.game,
            name="ToUpdate",
            slug="to-update",
            scope="full-game",
        )

        response = self.client.put(
            "/toupdate",
            json={"name": "Updated Variable"},
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "toupdate")
        self.assertEqual(data["name"], "Updated Variable")

    def test_delete_variable(self) -> None:
        """Test DELETE /variables/{id} endpoint deletes a variable."""
        Variables.objects.create(
            id="todelete",
            game=self.game,
            name="ToDelete",
            slug="to-delete",
            scope="full-game",
        )

        response = self.client.delete(
            "/todelete",
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("deleted successfully", data["message"])
        self.assertFalse(Variables.objects.filter(id="todelete").exists())


class APIVariableValuesTestCase(TestCase):
    """Tests for Variable Values API endpoints (GET)."""

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

        cls.variable = Variables.objects.create(
            id="var1",
            name="Difficulty",
            slug="difficulty",
            game=cls.game,
            scope="full-game",
            archive=False,
        )

        cls.value1 = VariableValues.objects.create(
            var=cls.variable,
            name="Normal",
            slug="normal",
            value="val1",
            archive=False,
            rules="Normal difficulty rules",
        )

        cls.value2 = VariableValues.objects.create(
            var=cls.variable,
            name="Hard",
            slug="hard",
            value="val2",
            archive=False,
            rules="Hard difficulty rules",
        )

    def setUp(self) -> None:
        self.client = TestClient(variables_router)

    def test_get_all_values_requires_variable_id(self) -> None:
        """Test GET /variables/values/all requires variable_id parameter."""
        response = self.client.get("/values/all")
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "Please provide the variable's unique ID.")

    def test_get_all_values_with_variable_id(self) -> None:
        """Test GET /variables/values/all?variable_id=var1 endpoint."""
        response = self.client.get("/values/all?variable_id=var1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)
        # Values should be ordered by name
        names = [v["name"] for v in data]
        self.assertIn("Normal", names)
        self.assertIn("Hard", names)

    def test_get_all_values_with_embed(self) -> None:
        """Test GET /variables/values/all?variable_id=var1&embed=variable endpoint."""
        response = self.client.get("/values/all?variable_id=var1&embed=variable")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        # Each value should have the variable embedded
        for value in data:
            self.assertIsNotNone(value.get("variable"))
            self.assertEqual(value["variable"]["id"], "var1")
            self.assertEqual(value["variable"]["name"], "Difficulty")

    def test_get_all_values_invalid_embed(self) -> None:
        """Test GET /variables/values/all with invalid embed returns error."""
        response = self.client.get("/values/all?variable_id=var1&embed=invalid")
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("Invalid embed", data["error"])

    def test_get_all_values_nonexistent_variable(self) -> None:
        """Test GET /variables/values/all with non-existent variable returns 404."""
        response = self.client.get("/values/all?variable_id=nonexistent")
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data["error"], "Variable does not exist")

    def test_get_value_by_id(self) -> None:
        """Test GET /variables/values/{value_id} endpoint."""
        response = self.client.get("/values/val1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["value"], "val1")
        self.assertEqual(data["name"], "Normal")
        self.assertEqual(data["slug"], "normal")
        self.assertEqual(data["rules"], "Normal difficulty rules")

    def test_get_value_by_id_with_embed(self) -> None:
        """Test GET /variables/values/{value_id}?embed=variable endpoint."""
        response = self.client.get("/values/val1?embed=variable")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["value"], "val1")
        self.assertIsNotNone(data.get("variable"))
        self.assertEqual(data["variable"]["id"], "var1")
        self.assertEqual(data["variable"]["name"], "Difficulty")

    def test_get_value_not_found(self) -> None:
        """Test GET /variables/values/{value_id} returns 404 for non-existent value."""
        response = self.client.get("/values/noexist")
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data["error"], "Variable value does not exist")

    def test_get_value_id_too_long(self) -> None:
        """Test GET /variables/values/{value_id} returns error for ID > 10 chars."""
        response = self.client.get("/values/thisiswaytoolong")
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "Value ID must be 10 characters or less")


class APIVariableValuesWriteTestCase(AuthenticatedAPITestCase):
    """Tests for Variable Values POST/PUT/DELETE endpoints."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.variable = Variables.objects.create(
            id="var1",
            name="Difficulty",
            slug="difficulty",
            game=cls.game,
            scope="full-game",
            archive=False,
        )

        cls.value = VariableValues.objects.create(
            var=cls.variable,
            name="Normal",
            slug="normal",
            value="val1",
            archive=False,
        )

    def setUp(self) -> None:
        super().setUp()
        self.client = TestClient(variables_router)

    def test_create_value(self) -> None:
        """Test POST /variables/values/ endpoint creates a new value."""
        response = self.client.post(
            "/values/",
            json={
                "variable_id": "var1",
                "name": "Easy",
                "rules": "Easy difficulty rules",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "Easy")
        self.assertEqual(data["slug"], "easy")  # Auto-generated from name
        self.assertEqual(data["rules"], "Easy difficulty rules")
        # Value ID should be auto-generated
        self.assertIsNotNone(data.get("value"))
        self.assertEqual(len(data["value"]), 8)

    def test_create_value_with_custom_id(self) -> None:
        """Test POST /variables/values/ with custom value ID."""
        response = self.client.post(
            "/values/",
            json={
                "value": "hardmode",
                "variable_id": "var1",
                "name": "Hard Mode",
                "slug": "hard-mode",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["value"], "hardmode")
        self.assertEqual(data["name"], "Hard Mode")
        self.assertEqual(data["slug"], "hard-mode")

    def test_create_value_duplicate_id_fails(self) -> None:
        """Test POST /variables/values/ with existing ID returns error."""
        response = self.client.post(
            "/values/",
            json={
                "value": "val1",  # Already exists
                "variable_id": "var1",
                "name": "Duplicate",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "Value ID Already Exists")

    def test_create_value_nonexistent_variable_fails(self) -> None:
        """Test POST /variables/values/ with non-existent variable returns error."""
        response = self.client.post(
            "/values/",
            json={
                "variable_id": "nonexistent",
                "name": "Test",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "Variable does not exist")

    def test_update_value(self) -> None:
        """Test PUT /variables/values/{value_id} endpoint updates a value."""
        response = self.client.put(
            "/values/val1",
            json={
                "name": "Updated Normal",
                "rules": "Updated rules",
                "archive": True,
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["value"], "val1")
        self.assertEqual(data["name"], "Updated Normal")
        self.assertEqual(data["rules"], "Updated rules")
        self.assertEqual(data["archive"], True)

    def test_update_value_change_variable(self) -> None:
        """Test PUT /variables/values/{value_id} can change parent variable."""
        # Create another variable
        Variables.objects.create(
            id="var2",
            name="Platform",
            slug="platform",
            game=self.game,
            scope="full-game",
        )

        response = self.client.put(
            "/values/val1",
            json={"variable_id": "var2"},
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["value"], "val1")

        # Verify the value is now associated with var2
        val = VariableValues.objects.get(value="val1")
        self.assertEqual(val.var.id, "var2")

    def test_update_nonexistent_value_fails(self) -> None:
        """Test PUT /variables/values/{value_id} with non-existent ID returns 404."""
        response = self.client.put(
            "/values/nonexistent",
            json={"name": "Updated"},
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data["error"], "Variable value does not exist")

    def test_delete_value(self) -> None:
        """Test DELETE /variables/values/{value_id} endpoint deletes a value."""
        # Create a value to delete
        VariableValues.objects.create(
            var=self.variable,
            name="ToDelete",
            slug="to-delete",
            value="todel",
            archive=False,
        )

        response = self.client.delete(
            "/values/todel",
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("deleted successfully", data["message"])
        self.assertFalse(VariableValues.objects.filter(value="todel").exists())

    def test_delete_nonexistent_value_fails(self) -> None:
        """Test DELETE /variables/values/{value_id} with non-existent ID returns 404."""
        response = self.client.delete(
            "/values/nonexistent",
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data["error"], "Variable value does not exist")


class APIRunsWriteTestCase(AuthenticatedAPITestCase):
    """Tests for Runs POST/PUT/DELETE endpoints."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.category = Categories.objects.create(
            id="cat1",
            game=cls.game,
            name="Any%",
            slug="any",
            type="per-game",
            url="https://speedrun.com/test-game#any",
        )
        cls.level = Levels.objects.create(
            id="level1",
            game=cls.game,
            name="Warehouse",
            slug="warehouse",
            url="https://speedrun.com/test-game/Warehouse",
        )
        cls.il_category = Categories.objects.create(
            id="ilcat",
            game=cls.game,
            name="IL Any%",
            slug="il-any",
            type="per-level",
            url="https://speedrun.com/test-game#il-any",
        )
        cls.player = Players.objects.create(
            id="player1",
            name="TestPlayer",
            url="https://speedrun.com/user/TestPlayer",
        )

    def setUp(self) -> None:
        super().setUp()
        self.client = TestClient(runs_router)

    def test_create_run(self) -> None:
        """Test POST /runs/ endpoint creates a new run."""
        response = self.client.post(
            "/",
            json={
                "game_id": "game1",
                "category_id": "cat1",
                "runtype": "main",
                "place": 1,
                "url": "https://speedrun.com/test-game/run/new",
                "time": "5m 30s",
                "time_secs": 330.0,
                "player_ids": ["player1"],
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["time"], "5m 30s")
        self.assertEqual(data["place"], 1)
        # ID should be auto-generated
        self.assertIsNotNone(data.get("id"))
        self.assertEqual(len(data["id"]), 8)

    def test_create_run_with_custom_id(self) -> None:
        """Test POST /runs/ with custom ID."""
        response = self.client.post(
            "/",
            json={
                "id": "run001",
                "game_id": "game1",
                "category_id": "cat1",
                "runtype": "main",
                "place": 2,
                "url": "https://speedrun.com/test-game/run/run001",
                "time": "6m 00s",
                "time_secs": 360.0,
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "run001")

    def test_create_run_nonexistent_game_fails(self) -> None:
        """Test POST /runs/ with non-existent game returns error."""
        response = self.client.post(
            "/",
            json={
                "game_id": "nonexistent",
                "runtype": "main",
                "place": 1,
                "url": "https://speedrun.com/test/run/new",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "Game does not exist")

    def test_update_run(self) -> None:
        """Test PUT /runs/{id} endpoint updates a run."""
        Runs.objects.create(
            id="toupdate",
            game=self.game,
            category=self.category,
            runtype="main",
            place=5,
            url="https://speedrun.com/test-game/run/toupdate",
            time="10m 00s",
            time_secs=600.0,
        )

        response = self.client.put(
            "/toupdate",
            json={
                "place": 1,
                "time": "5m 00s",
                "time_secs": 300.0,
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "toupdate")
        self.assertEqual(data["place"], 1)
        self.assertEqual(data["time"], "5m 00s")

    def test_delete_run(self) -> None:
        """Test DELETE /runs/{id} endpoint deletes a run."""
        Runs.objects.create(
            id="todelete",
            game=self.game,
            category=self.category,
            runtype="main",
            place=1,
            url="https://speedrun.com/test-game/run/todelete",
        )

        response = self.client.delete(
            "/todelete",
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("deleted successfully", data["message"])
        self.assertFalse(Runs.objects.filter(id="todelete").exists())


class APIStreamsWriteTestCase(AuthenticatedAPITestCase):
    """Tests for Streams POST/PUT/DELETE endpoints."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.player = Players.objects.create(
            id="streamer1",
            name="StreamerPlayer",
            url="https://speedrun.com/user/StreamerPlayer",
            twitch="https://twitch.tv/streamerplayer",
        )
        cls.player2 = Players.objects.create(
            id="streamer2",
            name="StreamerPlayer2",
            url="https://speedrun.com/user/StreamerPlayer2",
            twitch="https://twitch.tv/streamerplayer2",
        )

    def setUp(self) -> None:
        super().setUp()
        self.client = TestClient(streams_router)

    def test_create_stream(self) -> None:
        """Test POST /streams/ endpoint creates a new stream."""
        response = self.client.post(
            "/",
            json={
                "player_id": "streamer1",
                "game_id": "game1",
                "title": "Test Stream!",
                "offline_ct": 0,
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["title"], "Test Stream!")
        self.assertIsNotNone(data.get("player"))

    def test_create_stream_duplicate_player_fails(self) -> None:
        """Test POST /streams/ with existing streamer returns error."""
        # Create initial stream
        NowStreaming.objects.create(
            streamer=self.player2,
            game=self.game,
            title="Already Streaming",
            offline_ct=0,
            stream_time=timezone.now(),
        )

        response = self.client.post(
            "/",
            json={
                "player_id": "streamer2",
                "game_id": "game1",
                "title": "Another Stream",
                "offline_ct": 0,
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("already has an active stream", data["error"])

    def test_update_stream(self) -> None:
        """Test PUT /streams/{player_id} endpoint updates a stream."""
        NowStreaming.objects.create(
            streamer=self.player,
            game=self.game,
            title="Original Title",
            offline_ct=0,
            stream_time=timezone.now(),
        )

        response = self.client.put(
            "/streamer1",
            json={"title": "Updated Title"},
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["title"], "Updated Title")

    def test_delete_stream(self) -> None:
        """Test DELETE /streams/{player_id} endpoint deletes a stream."""
        NowStreaming.objects.create(
            streamer=self.player,
            game=self.game,
            title="To Delete",
            offline_ct=0,
            stream_time=timezone.now(),
        )

        response = self.client.delete(
            "/streamer1",
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("deleted successfully", data["message"])
        self.assertFalse(NowStreaming.objects.filter(streamer=self.player).exists())
