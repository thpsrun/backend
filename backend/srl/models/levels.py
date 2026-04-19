from django.db import models
from django.utils.text import slugify

from srl.models.games import Games


class Levels(models.Model):
    class Meta:
        verbose_name_plural = "Levels"
        ordering = ["name"]

    id = models.CharField(
        max_length=10,
        primary_key=True,
        verbose_name="Level ID",
    )
    game = models.ForeignKey(
        Games,
        verbose_name="Linked Game",
        null=True,
        on_delete=models.PROTECT,
    )
    name = models.CharField(
        max_length=75,
        verbose_name="Name",
    )
    slug = models.SlugField(
        max_length=75,
        verbose_name="Slug",
        blank=True,
    )
    url = models.URLField(
        verbose_name="URL",
    )
    rules = models.TextField(
        max_length=5000,
        verbose_name="Rules",
        blank=True,
        null=True,
    )
    order = models.IntegerField(
        verbose_name="Sort Order",
        default=0,
        help_text=(
            "Controls display order. order=0 items sort alphabetically as a fallback. "
            "Items with order>=1 sort first in ascending order."
        ),
    )
    archive = models.BooleanField(
        verbose_name="Archive Level",
        default=False,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
