import os
from pathlib import Path

import sentry_sdk
from celery.schedules import crontab
from corsheaders.defaults import default_headers as _cors_default_headers
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.getenv("DEBUG_MODE") == "True"


def _require_env(
    name: str,
) -> str:
    value: str | None = os.getenv(name)
    if not value:
        raise ImproperlyConfigured(f"{name} environmental variable is not set")
    return value


if os.getenv("SENTRY_ENABLED") == "True":
    sentry_sdk.init(
        dsn=os.getenv("SENTRY_DSN"),
        send_default_pii=False,
        traces_sample_rate=0.5,
    )

SECRET_KEY = _require_env("SECRET_KEY")

if DEBUG:
    ALLOWED_HOSTS = [
        h.strip() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip()
    ]
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
else:
    ALLOWED_HOSTS = [
        h.strip() for h in _require_env("ALLOWED_HOSTS").split(",") if h.strip()
    ]
    if not ALLOWED_HOSTS:
        raise ImproperlyConfigured("ALLOWED_HOSTS must contain at least one host")
    FRONTEND_URL = _require_env("FRONTEND_URL")
# ALLOWED_IPS = ["127.0.0.1"]

INSTALLED_APPS = [
    # PRE-INSTALLED
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.postgres",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # LOCAL (accounts listed first so its templates override allauth's bundled ones)
    "accounts",
    # THIRD-PARTY
    "corsheaders",
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.discord",
    "allauth.socialaccount.providers.twitch",
    "allauth.mfa",
    "allauth.headless",
    "django_htmx",
    "rest_framework_api_key",
    "rules",
    # LOCAL
    "srl",
    "api",
    "auditlog",
    "notifications",
    "guides",
    "nav",
]

AUTH_USER_MODEL = "accounts.CustomUser"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "accounts.middleware.PathRateLimitMiddleware",
    "accounts.middleware.TurnstileMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "accounts.middleware.MFASetupRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "auditlog.middleware.AuditActorMiddleware",
    "api.middleware.APIActivityLogMiddleware",
    "accounts.middleware.OAuthPopupCOOPMiddleware",
]

CORS_ALLOWED_ORIGINS = [FRONTEND_URL]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = (
    *_cors_default_headers,
    "x-remember-me",
    "x-turnstile-token",
)

ROOT_URLCONF = "website.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

AUTHENTICATION_BACKENDS = [
    "rules.permissions.ObjectPermissionBackend",
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]


WSGI_APPLICATION = "website.wsgi.application"

if DEBUG:
    CORS_ALLOWED_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]
    CSRF_TRUSTED_ORIGINS = ["http://localhost:8001", "http://localhost:3000"]
    INSTALLED_APPS.append("debug_toolbar")
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")
else:
    APPEND_SLASH = True
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
    CSRF_TRUSTED_ORIGINS = [FRONTEND_URL]

    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB"),
        "USER": os.getenv("POSTGRES_USER"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD"),
        "HOST": os.getenv("DATABASE_HOST", "postgres"),
        "CONN_MAX_AGE": 60,
    }
}

if DEBUG:
    redis_password = os.getenv("REDIS_PASSWORD", "")
else:
    redis_password = _require_env("REDIS_PASSWORD")
redis_auth = f":{redis_password}@" if redis_password else ""
REDIS_DB = f"redis://{redis_auth}redis:6379"

# Comma-separated IPs or CIDR ranges of trusted reverse proxies. When the request's
# REMOTE_ADDR matches one of these, X-Forwarded-For is honored for rate limiting and logging.
TRUSTED_PROXIES = os.getenv("TRUSTED_PROXIES", "")

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": f"{REDIS_DB}/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "SOCKET_CONNECT_TIMEOUT": 5,
            "SOCKET_TIMEOUT": 5,
        },
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_ROOT = os.path.join(BASE_DIR, "static")
STATIC_URL = "/static/"

# Media files (user-uploaded content)
MEDIA_ROOT = os.path.join(BASE_DIR, "media")
MEDIA_URL = "/media/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# CELERY SETTINGS
CELERY_BROKER_URL = f"{REDIS_DB}/0"
CELERY_RESULT_BACKEND = f"{REDIS_DB}/0"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_RESULT_EXTENDED = True
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_TASK_SOFT_TIME_LIMIT = 20 * 60  # catchable SoftTimeLimitExceeded before the hard SIGKILL
CELERY_WORKER_MAX_MEMORY_PER_CHILD = 350000  # KB (~350 MB); recycle child gracefully before OOM
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # a crash drops at most one message, not a prefetched batch

# CELERY BEAT SCHEDULE
CELERY_BEAT_SCHEDULE = {
    "build-streaks-daily": {
        "task": "srl.tasks.build_streaks_task",
        "schedule": crontab(hour=0, minute=0),
    },
    "sweep-stuck-reconciliation-jobs-15min": {
        "task": "srl.sweep_stuck_reconciliation_jobs",
        "schedule": crontab(minute="*/15"),
    },
    "scan-expiring-api-keys-daily": {
        "task": "notifications.scan_expiring_api_keys",
        "schedule": crontab(hour=12, minute=0),
    },
    "purge-old-notifications-daily": {
        "task": "notifications.purge_old_notifications",
        "schedule": crontab(hour=4, minute=0),
    },
    "purge-user-data-exports-daily": {
        "task": "accounts.purge_user_data_exports",
        "schedule": crontab(hour=2, minute=0),
    },
    # "prune-api-activity-log-daily": {
    #    "task": "srl.tasks.prune_api_activity_log",
    #    "schedule": crontab(hour=3, minute=15),
    # },
    "dispatch-run-discovery-1min": {
        "task": "srl.tasks.dispatch_run_discovery",
        "schedule": crontab(minute="*"),
    },
    "discover-series-games-5min": {
        "task": "srl.tasks.discover_new_series_games",
        "schedule": crontab(minute="*/5"),
    },
}

# POINTS CONSTANTS
POINTS_MAX_FG = 1000
POINTS_MAX_IL = 250
POINTS_MAX_CE = 50

# STREAK BONUS CONSTANTS
STREAK_BONUS_FG = 125
STREAK_BONUS_IL = 31.25
STREAK_MAX_MONTHS = 4

# NAVBAR
# Maximum NavItem nesting depth (root counts as level 1).
NAVBAR_MAX_DEPTH = 5

# SITE
SITE_ID = 1

# ALLAUTH SETTINGS
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS = 1
ACCOUNT_EMAIL_NOTIFICATIONS = True
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_CHANGE_EMAIL = True
# OAuth signups must confirm the email they supply. SRCSignupInput forces the address
# verified=False, so allauth's verification stage always fires; mirrors
# ACCOUNT_EMAIL_VERIFICATION above for the local registration path.
SOCIALACCOUNT_EMAIL_VERIFICATION = "mandatory"
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
PASSWORD_RESET_TIMEOUT = 1800
ACCOUNT_LOGIN_METHODS = {"username", "email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "username*", "password1*", "password2*"]
MFA_TOTP_ISSUER = os.getenv("SITE_NAME", "THPS Speedrunning")

SOCIALACCOUNT_ADAPTER = "accounts.adapters.SocialAccountAdapter"
MFA_ADAPTER = "accounts.adapters.MFAAdapter"

# This disables the auto-signup since we want to grab the user's SRC API Key for signup.
# This would just circumvent it.
SOCIALACCOUNT_AUTO_SIGNUP = False

MFA_SUPPORTED_TYPES = ["totp", "webauthn", "recovery_codes"]
MFA_PASSKEY_LOGIN_ENABLED = True
MFA_PASSKEY_SIGNUP_ENABLED = False
MFA_WEBAUTHN_ALLOW_INSECURE_ORIGIN = DEBUG  # WebAuthn refuses HTTP except on localhost

# Require superusers and game moderators to have a TOTP authenticator or a WebAuthn passkey
# before they can use the API (enforced by accounts.middleware.MFASetupRequiredMiddleware).
MFA_ENFORCE_FOR_PRIVILEGED = os.getenv("MFA_ENFORCE_FOR_PRIVILEGED", "True") == "True"
OAUTH_REAUTH_INTENT_TTL_SECONDS = int(
    os.getenv("OAUTH_REAUTH_INTENT_TTL_SECONDS", "600")
)
OAUTH_SIGNUP_INTENT_TTL_SECONDS = int(
    os.getenv("OAUTH_SIGNUP_INTENT_TTL_SECONDS", "600")
)
OAUTH_LOGIN_INTENT_TTL_SECONDS = int(os.getenv("OAUTH_LOGIN_INTENT_TTL_SECONDS", "600"))

# CLOUDFLARE TURNSTILE
# Site key is read by the frontend; backend stores it so a future config endpoint can
# expose it without duplicating across repos. The backend itself never sends the site key.
# In DEBUG, fall back to Cloudflare's always-pass dummy keys. In production both are
# required so a forgotten env var fails boot rather than silently stripping the
# Turnstile gate from login/password-reset/provider-signup endpoints.
if DEBUG:
    TURNSTILE_SITE_KEY = os.getenv(
        "TURNSTILE_SITE_KEY",
        "1x00000000000000000000AA",
    )
    TURNSTILE_SECRET_KEY = os.getenv(
        "TURNSTILE_SECRET_KEY",
        "1x0000000000000000000000000000000AA",
    )
else:
    TURNSTILE_SITE_KEY = _require_env("TURNSTILE_SITE_KEY")
    TURNSTILE_SECRET_KEY = _require_env("TURNSTILE_SECRET_KEY")
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TURNSTILE_TIMEOUT_SECONDS = 5

# Opt-in switch for PathRateLimitMiddleware. Default off (limits enforced everywhere).
# Local dev that legitimately needs to exceed the 3/hour budget can set
# RATE_LIMIT_DISABLED=True in .env; production must never set this.
RATE_LIMIT_DISABLED = os.getenv("RATE_LIMIT_DISABLED", "False").lower() == "true"

# Session life when `Remember Me` is not chosen (7 days) or, if set, 30 days.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7
REMEMBER_AGE = 60 * 60 * 24 * 30
AWAITING_REVIEW_NOTIFY_MAX_AGE_DAYS = 7

# SOCIAL AUTH (Discord + Twitch - apps registered externally, credentials in .env)
SOCIALACCOUNT_PROVIDERS = {
    "discord": {
        "SCOPE": ["identify", "email"],
        "APP": {
            "client_id": os.getenv("DISCORD_CLIENT_ID", ""),
            "secret": os.getenv("DISCORD_CLIENT_SECRET", ""),
        },
    },
    "twitch": {
        "SCOPE": ["user:read:email"],
        "APP": {
            "client_id": os.getenv("TWITCH_CLIENT_ID", ""),
            "secret": os.getenv("TWITCH_CLIENT_SECRET", ""),
        },
    },
}


# ALLAUTH HEADLESS
HEADLESS_ONLY = True
HEADLESS_FRONTEND_URLS = {
    "account_confirm_email": f"{FRONTEND_URL}/verify-email/{{key}}",
    "account_reset_password_from_key": f"{FRONTEND_URL}/reset-password/{{uidb36}}/{{key}}",
    "socialaccount_login_error": f"{FRONTEND_URL}/login/error/",
}

# EMAIL (Resend via django-anymail TODO:)
EMAIL_BACKEND = "anymail.backends.resend.EmailBackend"
ANYMAIL = {
    "RESEND_API_KEY": os.getenv("RESEND_API_KEY", ""),
}
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "noreply@thpsspeedrunning.com")
ACCOUNT_EMAIL_SUBJECT_PREFIX = "[thps.run] "

# SRC INTEGRATION
SRC_ENCRYPTION_KEY = os.getenv("SRC_ENCRYPTION_KEY")

SRC_V2_ENABLED = os.getenv("SRC_V2_ENABLED", "False").lower() == "true"
SRC_BOT_USERNAME = os.getenv("SRC_BOT_USERNAME", "")
SRC_BOT_PASSWORD = os.getenv("SRC_BOT_PASSWORD", "")
SRC_2FA_SENDER_EMAIL = os.getenv(
    "SRC_2FA_SENDER_EMAIL",
    "noreply@speedrun.com",
)
SRC_2FA_SUBJECT_PATTERN = os.getenv(
    "SRC_2FA_SUBJECT_PATTERN",
    r"verification code",
)
SRC_BOT_MAILBOX_IMAP_HOST = os.getenv(
    "SRC_BOT_MAILBOX_IMAP_HOST",
    "imap.gmail.com",
)
SRC_BOT_MAILBOX_PORT = int(os.getenv("SRC_BOT_MAILBOX_PORT", "993"))
SRC_BOT_MAILBOX_USER = os.getenv("SRC_BOT_MAILBOX_USER", "")
SRC_BOT_MAILBOX_APP_PASSWORD = os.getenv(
    "SRC_BOT_MAILBOX_APP_PASSWORD",
    "",
)
SRC_BOT_REFRESH_COOLDOWN = int(os.getenv("SRC_BOT_REFRESH_COOLDOWN", "30"))
SRC_BOT_2FA_WAIT_TIMEOUT = int(os.getenv("SRC_BOT_2FA_WAIT_TIMEOUT", "90"))
SRC_V2_USER_AGENT_SUFFIX = os.getenv(
    "SRC_V2_USER_AGENT_SUFFIX",
    "thps.run-bot",
)
SRC_V2_REPLAY_MAX_AGE_DAYS = int(
    os.getenv("SRC_V2_REPLAY_MAX_AGE_DAYS", "7"),
)

SRC_DISCOVERY_POLL_SECONDS = int(os.getenv("SRC_DISCOVERY_POLL_SECONDS", "60"))
SRC_DISCOVERY_PER_GAME_LIMIT = int(
    os.getenv("SRC_DISCOVERY_PER_GAME_LIMIT", "20"),
)
