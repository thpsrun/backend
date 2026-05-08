import os
from pathlib import Path

import sentry_sdk
from celery.schedules import crontab
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
    "accounts",
    "srl",
    "api",
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
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "api.middleware.APIActivityLogMiddleware",
]

CORS_ALLOWED_ORIGINS = [FRONTEND_URL]
CORS_ALLOW_CREDENTIALS = True

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

redis_password = os.getenv("REDIS_PASSWORD", "")
redis_auth = f":{redis_password}@" if redis_password else ""
REDIS_DB = f"redis://{redis_auth}redis:6379"

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

# API RATE LIMITING
RATELIMIT_RATE = "200/m"
RATELIMIT_RESPONSE = '{"ERROR": "Too many requests. Please try again later."}'
RATELIMIT_ENABLE = True


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

# CELERY BEAT SCHEDULE
CELERY_BEAT_SCHEDULE = {
    "build-streaks-daily": {
        "task": "srl.tasks.build_streaks_task",
        "schedule": crontab(hour=0, minute=0),
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

# SITE
SITE_ID = 1

# ALLAUTH SETTINGS
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_LOGIN_METHODS = {"username", "email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "username*", "password1*", "password2*"]
MFA_TOTP_ISSUER = os.getenv("SITE_NAME", "THPS Speedrunning")

SOCIALACCOUNT_ADAPTER = "accounts.adapters.SocialAccountAdapter"
MFA_ADAPTER = "accounts.adapters.MFAAdapter"

MFA_SUPPORTED_TYPES = ["totp", "webauthn", "recovery_codes"]
MFA_PASSKEY_LOGIN_ENABLED = True
MFA_PASSKEY_SIGNUP_ENABLED = False
MFA_WEBAUTHN_ALLOW_INSECURE_ORIGIN = DEBUG  # WebAuthn refuses HTTP except on localhost

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

SESSION_COOKIE_AGE = 60 * 60 * 24 * 7  # 7 days in seconds

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
ACCOUNT_EMAIL_SUBJECT_PREFIX = "[THPS Speedrunning] "

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
