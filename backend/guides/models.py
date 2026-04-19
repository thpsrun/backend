from django.db import models
from django.utils.text import slugify
from srl.models.games import Games


class Tags(models.Model):
    class Meta:
        verbose_name_plural = "Tags"
        ordering = ["name"]

    name = models.CharField(
        max_length=100,
        verbose_name="Tag Name",
    )
    slug = models.SlugField(
        max_length=100,
        unique=True,
        verbose_name="Slug",
    )
    description = models.TextField(
        max_length=100,
        verbose_name="Description",
    )

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Guides(models.Model):
    class Meta:
        verbose_name_plural = "Guides"
        ordering = ["-created_at", "title"]

    # submitted_user = models.ForeignKey(
    #     User,
    #     on_delete=models.CASCADE,
    #     verbose_name="Submitted User",
    #     help_text="User who submitted this guide",
    # )

    title = models.CharField(
        max_length=200,
        verbose_name="Guide Title",
    )
    slug = models.SlugField(
        max_length=200,
        unique=True,
        verbose_name="Slug",
    )
    tags = models.ManyToManyField(
        Tags,
        verbose_name="Tags",
        blank=True,
    )
    game = models.ForeignKey(
        Games,
        on_delete=models.PROTECT,
        verbose_name="Associated Game",
    )
    short_description = models.TextField(
        max_length=500,
        verbose_name="Short Description",
        help_text="Brief description of what this guide covers.",
    )
    content = models.TextField(
        verbose_name="Guide Content",
        help_text="Full guide content; markdown is allowed.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Created At:",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Updated At:",
    )

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} ({self.game.name})"
