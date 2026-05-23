from notifications.registry import NotificationKind, register

RUN_APPROVED = "run_approved"
RUN_DENIED = "run_denied"
MOD_PROMOTED = "mod_promoted"
API_KEY_EXPIRING = "api_key_expiring"
RUN_REVIEW = "run_review"
USER_DATA_EXPORT_READY = "user_data_export_ready"
USER_DATA_EXPORT_FAILED = "user_data_export_failed"


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
        key=USER_DATA_EXPORT_READY,
        label="Data Export Ready",
        description="Your account data export is ready to download.",
    ),
)
register(
    NotificationKind(
        key=USER_DATA_EXPORT_FAILED,
        label="Data Export Failed",
        description="Your account data export failed. You can try again now.",
    ),
)
