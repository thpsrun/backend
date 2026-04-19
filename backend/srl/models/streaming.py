from django.db import models

from srl.models.games import Games
from srl.models.players import Players


class NowStreaming(models.Model):
    class Meta:
        verbose_name = "Stream"
        verbose_name_plural = "Streams"

    streamer = models.OneToOneField(
        Players,
        primary_key=True,
        verbose_name="Streamer",
        on_delete=models.CASCADE,
    )
    game = models.ForeignKey(
        Games,
        verbose_name="Game",
        null=True,
        on_delete=models.PROTECT,
    )
    title = models.CharField(
        max_length=100,
        verbose_name="Twitch Title",
    )
    offline_ct = models.PositiveSmallIntegerField(
        verbose_name="Offline Count",
        help_text=(
            "In some situations, bots or the Twitch API can mess up. To help users, "
            "you can use this counter to countup the number of attempts to see if the runner "
            "is offline. After a certain number is hit, you can do something like remove "
            "embeds and/or remove this record."
        ),
    )
    stream_time = models.DateTimeField(
        verbose_name="Started Stream",
    )

    def __str__(self):
        return f"Streaming: {self.streamer.name}"
