from django.db import models


class Series(models.Model):
    class Meta:
        verbose_name_plural = "Series"

    id = models.CharField(
        max_length=10,
        primary_key=True,
        verbose_name="Series ID",
    )
    name = models.CharField(
        max_length=80,
        verbose_name="Name",
    )
    url = models.URLField(
        verbose_name="URL",
    )

    def __str__(self):
        return self.name
