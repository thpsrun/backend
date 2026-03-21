from django.db import models


class SRCCredential(models.Model):
    class Meta:
        verbose_name = "SRC Credential"
        verbose_name_plural = "SRC Credentials"

    user = models.OneToOneField(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="src_credential",
    )
    encrypted_api_key = models.TextField(
        verbose_name="Encrypted SRC API Key",
        help_text="Encrypted SRC API key. Never expose this value in any API response.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(
        self,
    ) -> str:
        return f"SRC Credential for {self.user.username}"
