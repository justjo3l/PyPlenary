# -*- coding: utf-8 -*-
from pathlib import Path
import os
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    value = env(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=None):
    value = env(name)
    if not value:
        return default or []
    return [item.strip() for item in value.split(",") if item.strip()]


TIMEZONE_ALIASES = {
    "Brisbane time (Australian Eastern Standard Time)": "Australia/Brisbane",
    "Australian Eastern Standard Time": "Australia/Brisbane",
    "AEST": "Australia/Brisbane",
    "AEDT": "Australia/Melbourne",
    "Melbourne time": "Australia/Melbourne",
    "Sydney time": "Australia/Sydney",
    "Brisbane time": "Australia/Brisbane",
}


def normalize_timezone(value):
    timezone = TIMEZONE_ALIASES.get(value, value)
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        if DJANGO_DEVELOPMENT:
            return "Australia/Melbourne"
        raise RuntimeError(
            f"PYPLENARY_TZ must be an IANA timezone such as Australia/Brisbane, not {value!r}."
        )
    return timezone


DEBUG = env_bool("DEBUG_MODE", False)
DJANGO_DEVELOPMENT = env_bool("DJANGO_DEVELOPMENT", DEBUG)

SECRET_KEY = env("SECRET_KEY")
if not SECRET_KEY:
    if DJANGO_DEVELOPMENT:
        SECRET_KEY = "dev-only-insecure-secret-key"
    else:
        raise RuntimeError("SECRET_KEY must be set when DJANGO_DEVELOPMENT is false.")

WEB_DOMAIN = env("COUNCIL_URL", "http://localhost:8000" if DJANGO_DEVELOPMENT else None)
if not WEB_DOMAIN and not DEBUG:
    raise RuntimeError("COUNCIL_URL must be set in production.")

parsed_web_domain = urlparse(WEB_DOMAIN) if WEB_DOMAIN else None
default_hosts = ["localhost", "127.0.0.1", "[::1]"] if DJANGO_DEVELOPMENT else []
if parsed_web_domain and parsed_web_domain.hostname:
    default_hosts.append(parsed_web_domain.hostname)

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", default_hosts)
CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS",
    [WEB_DOMAIN] if WEB_DOMAIN and parsed_web_domain and parsed_web_domain.scheme in {"http", "https"} else [],
)

CUSTOM_CONFIGS = {
    "COUNCIL_URL": WEB_DOMAIN,
    "DBHOST": env("PGHOST"),
    "DBDOMAIN": env("PGDOMAIN", ""),
    "DBNAME": env("PGDATABASE"),
    "DBUSER": env("PGUSER"),
    "DBPORT": env("PGPORT", "5432"),
    "DEBUG_MODE": env("DEBUG_MODE", "0"),
    "EMAIL_HOST_USER": env("EMAIL_HOST_USER"),
    "REDIS_URL": env("REDIS_URL"),
    "REGO_OPEN": env("REGO_OPEN", "0"),
    "USER_TEMP_PASSWORD": env("USER_TEMP_PASSWORD"),
    "PYPLENARY_NAVBAR_NAME": env("PYPLENARY_NAVBAR_NAME", "PyPlenary"),
    "PYPLENARY_SITE_NAME": env("PYPLENARY_SITE_NAME", "PyPlenary"),
    "PYPLENARY_SITE_TAGLINE": env("PYPLENARY_SITE_TAGLINE", ""),
    "PYPLENARY_AGENDA_URI": env("PYPLENARY_AGENDA_URI"),
    "PYPLENARY_REPORTS_URI": env("PYPLENARY_REPORTS_URI"),
    "PYPLENARY_POLICIES_URI": env("PYPLENARY_POLICIES_URI"),
    "PYPLENARY_SOCIALS_URI": env("PYPLENARY_SOCIALS_URI"),
    "PYPLENARY_NODES_URI": env("PYPLENARY_NODES_URI"),
    "PYPLENARY_FACEBOOK_GROUP": env("PYPLENARY_FACEBOOK_GROUP"),
    "PYPLENARY_TZ": normalize_timezone(env("PYPLENARY_TZ", "Australia/Melbourne")),
    "PYPLENARY_ADMIN_NAME": env("PYPLENARY_ADMIN_NAME", "Joel Jose"),
    "PYPLENARY_ADMIN_EMAIL": env("PYPLENARY_ADMIN_EMAIL", env("EMAIL_HOST_USER", "admin@example.com")),
    "PYPLENARY_SUPPORT_EMAIL": env("PYPLENARY_SUPPORT_EMAIL", env("DEFAULT_FROM_EMAIL", env("EMAIL_HOST_USER", "admin@example.com"))),
}

INSTALLED_APPS = [
    "channels",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "councilApp",
    "crispy_forms",
    "django_extensions",
    "crispy_forms_semantic_ui",
    "crispy_bootstrap4",
    "whitenoise.runserver_nostatic",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "pyplenary.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "scripts"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "pyplenary.context_processors.pyplenary_settings",
            ],
        },
    },
]

WSGI_APPLICATION = "pyplenary.wsgi.application"
ASGI_APPLICATION = "pyplenary.asgi.application"

REDIS_URL = CUSTOM_CONFIGS["REDIS_URL"]
if REDIS_URL:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [REDIS_URL]},
        },
    }
else:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        },
    }

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = CUSTOM_CONFIGS["PYPLENARY_TZ"]
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = []
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
WHITENOISE_MANIFEST_STRICT = env_bool("WHITENOISE_MANIFEST_STRICT", False)

CRISPY_ALLOWED_TEMPLATE_PACKS = ("bootstrap4",)
CRISPY_TEMPLATE_PACK = "bootstrap4"

PYPLENARY_NAVBAR_NAME = CUSTOM_CONFIGS["PYPLENARY_NAVBAR_NAME"]
PYPLENARY_SITE_NAME = CUSTOM_CONFIGS["PYPLENARY_SITE_NAME"]
PYPLENARY_SITE_TAGLINE = CUSTOM_CONFIGS["PYPLENARY_SITE_TAGLINE"]
PYPLENARY_AGENDA_URI = CUSTOM_CONFIGS["PYPLENARY_AGENDA_URI"]
PYPLENARY_REPORTS_URI = CUSTOM_CONFIGS["PYPLENARY_REPORTS_URI"]
PYPLENARY_POLICIES_URI = CUSTOM_CONFIGS["PYPLENARY_POLICIES_URI"]
PYPLENARY_SOCIALS_URI = CUSTOM_CONFIGS["PYPLENARY_SOCIALS_URI"]
PYPLENARY_NODES_URI = CUSTOM_CONFIGS["PYPLENARY_NODES_URI"]
PYPLENARY_FACEBOOK_GROUP = CUSTOM_CONFIGS["PYPLENARY_FACEBOOK_GROUP"]
PYPLENARY_TZ = CUSTOM_CONFIGS["PYPLENARY_TZ"]
PYPLENARY_ADMIN_NAME = CUSTOM_CONFIGS["PYPLENARY_ADMIN_NAME"]
PYPLENARY_ADMIN_EMAIL = CUSTOM_CONFIGS["PYPLENARY_ADMIN_EMAIL"]
PYPLENARY_SUPPORT_EMAIL = CUSTOM_CONFIGS["PYPLENARY_SUPPORT_EMAIL"]

if DJANGO_DEVELOPMENT:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    missing_db_vars = [
        name
        for name in ("PGHOST", "PGDATABASE", "PGUSER", "DBPASS")
        if not env(name)
    ]
    if missing_db_vars:
        raise RuntimeError(f"Missing required production database settings: {', '.join(missing_db_vars)}")

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": CUSTOM_CONFIGS["DBNAME"],
            "HOST": CUSTOM_CONFIGS["DBHOST"] + CUSTOM_CONFIGS["DBDOMAIN"],
            "USER": CUSTOM_CONFIGS["DBUSER"],
            "PASSWORD": env("DBPASS"),
            "PORT": CUSTOM_CONFIGS["DBPORT"],
            "OPTIONS": {"sslmode": env("PGSSLMODE", "require")},
        }
    }

if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "pyplenary-local-cache",
        }
    }

RESEND_API_KEY = env("RESEND_API_KEY")
RESEND_API_URL = env("RESEND_API_URL", "https://api.resend.com/emails")
RESEND_TIMEOUT = int(env("RESEND_TIMEOUT", "10"))
GMAIL_CLIENT_ID = env("GMAIL_CLIENT_ID")
GMAIL_CLIENT_SECRET = env("GMAIL_CLIENT_SECRET")
GMAIL_REFRESH_TOKEN = env("GMAIL_REFRESH_TOKEN")
GMAIL_TOKEN_URL = env("GMAIL_TOKEN_URL", "https://oauth2.googleapis.com/token")
GMAIL_SEND_URL = env("GMAIL_SEND_URL", "https://gmail.googleapis.com/gmail/v1/users/me/messages/send")
GMAIL_API_TIMEOUT = int(env("GMAIL_API_TIMEOUT", "10"))
EMAIL_PROVIDER = env("EMAIL_PROVIDER", "smtp").lower()

default_email_backend = "django.core.mail.backends.console.EmailBackend"
if not DJANGO_DEVELOPMENT:
    if EMAIL_PROVIDER == "gmail_api":
        default_email_backend = "councilApp.email_backends.GmailAPIEmailBackend"
    elif EMAIL_PROVIDER == "resend":
        default_email_backend = "councilApp.email_backends.ResendEmailBackend"
    else:
        default_email_backend = "django.core.mail.backends.smtp.EmailBackend"

EMAIL_BACKEND = env("EMAIL_BACKEND", default_email_backend)
EMAIL_HOST = env("EMAIL_HOST", "smtp.gmail.com")
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", True)
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", False)
EMAIL_PORT = int(env("EMAIL_PORT", "465"))
EMAIL_HOST_USER = CUSTOM_CONFIGS["EMAIL_HOST_USER"]
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
EMAIL_TIMEOUT = int(env("EMAIL_TIMEOUT", "10"))
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER or "webmaster@localhost")

USER_TEMP_PASSWORD = CUSTOM_CONFIGS["USER_TEMP_PASSWORD"]
if not USER_TEMP_PASSWORD and not DJANGO_DEVELOPMENT:
    raise RuntimeError("USER_TEMP_PASSWORD must be set in production.")

LOADERIO_TOKEN = env("LOADERIO_TOKEN", "")
REGO_OPEN = env_bool("REGO_OPEN", False)

SESSION_COOKIE_SECURE = not DJANGO_DEVELOPMENT
CSRF_COOKIE_SECURE = not DJANGO_DEVELOPMENT
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", not DJANGO_DEVELOPMENT)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = int(env("SECURE_HSTS_SECONDS", "31536000" if not DJANGO_DEVELOPMENT else "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", not DJANGO_DEVELOPMENT)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)
X_FRAME_OPTIONS = "DENY"
