from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from accounts.models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    fieldsets = list(UserAdmin.fieldsets or []) + [
        (
            "Profile",
            {
                # Due to how Django users are handled, adding fields from models.py is a manual
                # process. Otherwise, it will look really stupid on the admin panel.
                "fields": (
                    "short_bio",
                    "bio",
                    "therun_gg",
                    "gradient_1",
                    "gradient_2",
                    "gradient_3",
                    "profile_bg",
                ),
            },
        ),
        (
            "SRC Integration",
            {
                "fields": ("encrypted_api_key",),
            },
        ),
    ]
