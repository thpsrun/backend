from django.db import models
from django_resized import ResizedImageField

from srl.models.base import validate_flag_image


class CountryCodes(models.Model):
    class Meta:
        verbose_name_plural = "Country Codes"
        ordering = ["name"]

    id = models.CharField(
        max_length=10,
        primary_key=True,
        verbose_name="Country Code ID",
    )
    name = models.CharField(
        max_length=50,
        verbose_name="Country Name",
    )
    flag = ResizedImageField(
        size=[72, 48],
        upload_to="flags",
        verbose_name="Custom Flag",
        validators=[validate_flag_image],
        null=True,
        blank=True,
        help_text=(
            "Custom flag image for countries not in the frontend flag library. "
            "Must have 1.5 aspect ratio (e.g. 72x48). Max 3MB."
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        return self.name
