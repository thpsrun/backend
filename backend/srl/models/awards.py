from django.db import models
from django_resized import ResizedImageField

from srl.models.base import validate_image


class Awards(models.Model):
    class Meta:
        verbose_name_plural = "Awards"

    name = models.CharField(
        max_length=50,
        verbose_name="Award Name",
        unique=True,
    )
    image = ResizedImageField(
        size=[64, 64],
        upload_to="awards",
        verbose_name="Image",
        validators=[validate_image],
        null=True,
        blank=True,
        help_text=(
            "Note: Images must be at least 64px in size, must be a square (height "
            "and width must match), and the max filesize is 3MB."
        ),
    )
    description = models.CharField(
        max_length=500,
        verbose_name="Award Description",
        blank=True,
        null=True,
    )

    def __str__(self):
        return self.name
