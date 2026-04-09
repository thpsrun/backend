from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from accounts.models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (
            "Profile",
            {
                "fields": (
                    "short_bio",
                    "bio",
                    "gradient_1",
                    "gradient_2",
                    "gradient_3",
                ),
            },
        ),
        (
            "SRC Integration",
            {
                "fields": ("encrypted_api_key",),
            },
        ),
    )
