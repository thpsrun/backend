from api.v1.routers.resources.streams import router as streams_router
from django.test import TestCase
from django.utils import timezone
from ninja.testing import TestClient
from srl.models import Games, NowStreaming, Platforms, Players

from tests.test_auth import AuthTestBase


class StreamsReadTest(TestCase):

    @classmethod
    def setUpTestData(
        cls,
    ) -> None:
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

    def setUp(
        self,
    ) -> None:
        self.client = TestClient(streams_router)  # type: ignore

    def test_live_streams(
        self,
    ) -> None:
        response = self.client.get("/live")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0, "Expected at least one live stream")
        first_stream = data[0]
        self.assertEqual(first_stream.get("title"), "Testing my speedruns!")
        self.assertEqual(first_stream["player"]["id"], "player1")
        self.assertEqual(first_stream["game"]["id"], "game1")

    def test_live_streams_filter_by_game(
        self,
    ) -> None:
        response = self.client.get("/live?game_id=game1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(len(data), 0)
        for stream in data:
            self.assertEqual(stream["game"]["id"], "game1")

    def test_live_streams_filter_no_match(
        self,
    ) -> None:
        response = self.client.get("/live?game_id=does-not-exist")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_get_stream_by_player(
        self,
    ) -> None:
        response = self.client.get(f"/{self.player.id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["title"], "Testing my speedruns!")
        self.assertEqual(data["player"]["id"], "player1")
        self.assertEqual(data["game"]["id"], "game1")

    def test_get_stream_not_found(
        self,
    ) -> None:
        response = self.client.get("/no-such-player")
        self.assertEqual(response.status_code, 404)
        self.assertIn("does not exist", response.json()["error"])


class StreamsWriteTest(AuthTestBase):

    @classmethod
    def setUpTestData(
        cls,
    ) -> None:
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

    def setUp(
        self,
    ) -> None:
        super().setUp()
        self.client = TestClient(streams_router)  # type: ignore

    def test_create_stream(
        self,
    ) -> None:
        response = self.client.post(
            "/",
            json={
                "player_id": "streamer1",
                "game_id": "game1",
                "title": "Test Stream!",
                "offline_ct": 0,
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["title"], "Test Stream!")
        self.assertIsNotNone(data.get("player"))

    def test_create_stream_duplicate(
        self,
    ) -> None:
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
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("already has an active stream", data["error"])

    def test_update_stream(
        self,
    ) -> None:
        NowStreaming.objects.create(
            streamer=self.player,
            game=self.game,
            title="Original Title",
            offline_ct=0,
            stream_time=timezone.now(),
        )

        response = self.client.put(
            "/streamer1",
            json={"title": "Updated Title"},  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["title"], "Updated Title")

    def test_delete_stream(
        self,
    ) -> None:
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
