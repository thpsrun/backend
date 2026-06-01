from notifications.registry import (
    NotificationGroup,
    NotificationKind,
    register,
    register_group,
)

RUN_APPROVED = "run_approved"
RUN_DENIED = "run_denied"
MOD_PROMOTED = "mod_promoted"
API_KEY_EXPIRING = "api_key_expiring"
RUN_REVIEW = "run_review"
RUN_AWAITING_REVIEW = "run_awaiting_review"
USER_DATA_EXPORT_READY = "user_data_export_ready"
USER_DATA_EXPORT_FAILED = "user_data_export_failed"
USER_DATA_EXPORT_GROUP = "user_data_export"


register_group(
    NotificationGroup(
        key=USER_DATA_EXPORT_GROUP,
        label="Data Export",
        description="Notifications about your account data export.",
    ),
)

register(
    NotificationKind(
        key=RUN_APPROVED,
        label="Run Approved",
        description="One of your submitted runs was approved!",
    ),
)
register(
    NotificationKind(
        key=RUN_DENIED,
        label="Run Denied",
        description="One of your submitted runs was denied!",
    ),
)
register(
    NotificationKind(
        key=MOD_PROMOTED,
        label="Promoted to Moderator",
        description="You were promoted to moderator on a game!",
    ),
)
register(
    NotificationKind(
        key=API_KEY_EXPIRING,
        label="API Key Expiring",
        description="One of your API keys will expire within 3 days!",
    ),
)
register(
    NotificationKind(
        key=RUN_REVIEW,
        label="Run Sent For Review",
        description="A moderator sent one of your runs back with notes to address!",
    ),
)
register(
    NotificationKind(
        key=RUN_AWAITING_REVIEW,
        label="Run Awaiting Review",
        description="A run on a game you moderate is awaiting review.",
    ),
)
register(
    NotificationKind(
        key=USER_DATA_EXPORT_READY,
        label="Data Export Ready",
        description="Your account data export is ready to download.",
        group=USER_DATA_EXPORT_GROUP,
    ),
)
register(
    NotificationKind(
        key=USER_DATA_EXPORT_FAILED,
        label="Data Export Failed",
        description="Your account data export failed. You can try again now.",
        group=USER_DATA_EXPORT_GROUP,
    ),
)
