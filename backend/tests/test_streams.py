from api.v1.routers.resources.streams import router as streams_router
from django.test import TestCase
from django.utils import timezone
from ninja.testing import TestClient
from srl.models import Games, NowStreaming, Platforms, Players

from tests.test_auth import AuthTestBase


class StreamsReadTest(TestCase):

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

    def test_live_streams(self) -> None:
        response = self.client.get("/live")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0, "Expected at least one mock stream")
        first_stream = data[0]
        self.assertIsNotNone(first_stream.get("title"))
        self.assertIsNotNone(first_stream.get("player"))
        self.assertIsNotNone(first_stream.get("game"))


class StreamsWriteTest(AuthTestBase):

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

    def test_create_stream_duplicate(self) -> None:
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
