from django.conf import settings
from django.db import models

from srl.models.awards import Awards
from srl.models.country_codes import CountryCodes


class Players(models.Model):
    class Meta:
        verbose_name_plural = "Players"
        ordering = ["name"]
        indexes = [
            models.Index(
                fields=["name"],
                name="idx_players_name",
            ),
            models.Index(
                fields=["nickname"],
                name="idx_players_nickname",
            ),
        ]

    id = models.CharField(
        max_length=10,
        primary_key=True,
        verbose_name="Player ID",
    )
    name = models.CharField(
        max_length=30,
        verbose_name="Name",
        default="Anonymous",
    )
    nickname = models.CharField(
        max_length=30,
        verbose_name="Nickname",
        blank=True,
        null=True,
        help_text=(
            "This is a special field where,  if a nickname is given, it will be "
            "shown versus their SRC name."
        ),
    )
    url = models.URLField(
        verbose_name="URL",
    )
    countrycode = models.ForeignKey(
        CountryCodes,
        verbose_name="Country Code",
        blank=True,
        null=True,
        on_delete=models.PROTECT,
    )
    pfp = models.CharField(
        max_length=100,
        verbose_name="Profile Picture URL",
        blank=True,
        null=True,
    )
    pronouns = models.CharField(
        max_length=50,
        verbose_name="Pronouns",
        blank=True,
        null=True,
    )
    twitch = models.URLField(
        verbose_name="Twitch",
        blank=True,
        null=True,
    )
    youtube = models.URLField(
        verbose_name="YouTube",
        blank=True,
        null=True,
    )
    twitter = models.URLField(
        verbose_name="Twitter",
        blank=True,
        null=True,
    )
    bluesky = models.URLField(
        verbose_name="Bluesky",
        blank=True,
        null=True,
    )
    discord = models.CharField(
        max_length=32,
        verbose_name="Discord",
        blank=True,
        null=True,
    )
    ex_stream = models.BooleanField(
        verbose_name="Stream Exception",
        default=False,
        help_text=(
            "When checked, this player can be filtered out from appearing on stream "
            "bots or pages."
        ),
    )
    awards = models.ManyToManyField(
        Awards,
        verbose_name="Awards",
        blank=True,
        help_text=(
            "Earned awards can be selected here. All selected awards will appear on "
            "the Player's profile."
        ),
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="player",
    )

    class ClaimStatus(models.TextChoices):
        UNCLAIMED = "unclaimed", "Unclaimed"
        CLAIMED = "claimed", "Claimed"
        DELETED = "deleted", "Deleted"

    claim_status = models.CharField(
        max_length=10,
        choices=ClaimStatus.choices,
        default=ClaimStatus.UNCLAIMED,
        verbose_name="Claim Status",
        help_text="Tracks whether a player account is unclaimed, actively claimed, or deleted.",
    )
    sync_paused = models.BooleanField(
        verbose_name="Sync Paused",
        default=False,
        help_text="When checked, SRC sync will skip this player.",
    )
    joined = models.DateField(
        verbose_name="Joined",
        blank=True,
        null=True,
        help_text="Date of the player's earliest verified speedrun.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        return self.name
