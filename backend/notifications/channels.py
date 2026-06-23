IN_APP = "in_app"
EMAIL = "email"

ALL_CHANNELS: tuple[str, ...] = (IN_APP, EMAIL)

DEFAULT_CHANNELS: dict[str, bool] = {
    IN_APP: True,
    EMAIL: False,
}
