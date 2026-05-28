IN_APP = "in_app"
EMAIL = "email"

ALL_CHANNELS: tuple[str, ...] = (IN_APP, EMAIL)

CHANNEL_LABELS: dict[str, str] = {
    IN_APP: "In-app",
    EMAIL: "Email",
}

DEFAULT_CHANNELS: dict[str, bool] = {
    IN_APP: True,
    EMAIL: False,
}
