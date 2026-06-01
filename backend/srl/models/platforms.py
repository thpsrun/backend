from django.db import models
from django.utils.text import slugify


class Platforms(models.Model):
    class Meta:
        verbose_name_plural = "Platforms"
        ordering = ["name"]

    id = models.CharField(
        max_length=10,
        primary_key=True,
        verbose_name="Platform ID",
    )
    name = models.CharField(
        max_length=30,
        verbose_name="Name",
    )
    slug = models.SlugField(
        max_length=30,
        verbose_name="Slug",
        blank=True,
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
