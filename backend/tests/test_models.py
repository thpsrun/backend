from django.test import Client, TestCase
from django.utils import timezone
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


class HomepageTest(TestCase):
    def setUp(self) -> None:
        self.client = Client()

    def test_homepage_404(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 404)


class ModelTest(TestCase):
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

        cls.country = CountryCodes.objects.create(id="usa", name="United States")

        cls.player1 = Players.objects.create(
            id="player1",
            name="Bob",
            nickname="Bobby B",
            url="https://speedrun.com/",
            countrycode=cls.country,
            pfp="https://google.com/",
            pronouns="He/Him/Them/They",
            twitch="Twitch",
            youtube="Youtube",
            twitter="Twitter",
            bluesky="Bluesky",
            discord="Discord",
            ex_stream=True,
        )
        cls.player1.awards.add(cls.awards)

        cls.player2 = Players.objects.create(
            id="player2",
            name="Sam",
            nickname="Sammy",
            url="https://speedrun.com/",
            countrycode=cls.country,
            pfp="https://google.com/",
            pronouns="He/Him/Them/They",
            twitch="Twitch",
            youtube="Youtube",
            twitter="Twitter",
            bluesky="Bluesky",
            discord="Discord",
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

        RunPlayers.objects.create(
            run=cls.runs,
            player=cls.player2,
            order=1,
        )

        cls.run_var_val = RunVariableValues.objects.create(
            id=1,
            run=cls.runs,
            variable=cls.variables,
            value=cls.values,
        )

        cls.stream = NowStreaming.objects.create(
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

    def test_variable_values(self) -> None:
        self.assertTrue(VariableValues.objects.filter(value="val1").exists())

    def test_players(self) -> None:
        self.assertTrue(Players.objects.filter(id="player1").exists())
        self.assertTrue(Players.objects.filter(id="player2").exists())

    def test_runs(self) -> None:
        self.assertTrue(Runs.objects.filter(id="run123").exists())
        self.assertTrue(RunVariableValues.objects.filter(id=1).exists())

    def test_streaming(self) -> None:
        self.assertTrue(NowStreaming.objects.all().exists())
