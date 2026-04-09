from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"

    encrypted_api_key = models.TextField(
        verbose_name="Encrypted SRC API Key",
        null=True,
        blank=True,
        help_text="Fernet-encrypted Speedrun.com API key. Never expose in API responses.",
    )
    bio = models.TextField(
        verbose_name="Biography",
        max_length=1000,
        null=True,
        blank=True,
        help_text="Markdown-formatted biography. Max 1000 characters.",
    )
    short_bio = models.CharField(
        verbose_name="Short Bio",
        max_length=100,
        null=True,
        blank=True,
        help_text="Brief bio displayed on profile. Max 100 characters. Emojis allowed.",
    )
    gradient_1 = models.CharField(
        verbose_name="Gradient Color 1",
        max_length=7,
        null=True,
        blank=True,
        help_text="Hex color for name gradient (#RRGGBB). Primary/solid color.",
    )
    gradient_2 = models.CharField(
        verbose_name="Gradient Color 2",
        max_length=7,
        null=True,
        blank=True,
        help_text="Hex color for name gradient (#RRGGBB). Requires gradient_1.",
    )
    gradient_3 = models.CharField(
        verbose_name="Gradient Color 3",
        max_length=7,
        null=True,
        blank=True,
        help_text="Hex color for name gradient (#RRGGBB). Requires gradient_2.",
    )
