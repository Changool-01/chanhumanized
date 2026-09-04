"""
Django settings for Chan Humanized AI.

Secrets and host-specific values come from environment variables (.env locally,
PythonAnywhere web-app environment later). SQLite is the default so the demo
runs without Docker; set DJANGO_DB=mysql for MySQL 8.
"""

import sys
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    DJANGO_DB=(str, "sqlite"),
    MYSQL_PORT=(int, 3306),
    OPENAI_MODEL=(str, "gpt-4o-mini"),
    # Security hardening settings.
    DEVELOPER_EMAIL=(str, ""),
    SECURITY_STRICT_DEVICE_IP=(bool, True),
    SECURITY_EMAIL_ON_LOCKOUT=(bool, True),
)

# Load .env if present (missing file is fine on PythonAnywhere when env vars are set).
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="unsafe-dev-key-change-me")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")
if DEBUG:
    for host in ("localhost", "127.0.0.1", "testserver", "192.168.221.88"):
        if host not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(host)

# Product copy used in templates (keep the public name in one place).
SITE_NAME = "Chan Humanized AI"

# Security contact / alert settings.
# DEVELOPER_EMAIL receives the alert when an account is permanently locked.
# Set it in your .env or PythonAnywhere web app environment.
DEVELOPER_EMAIL = env("DEVELOPER_EMAIL") or "noreply@chan-humanized-ai.local"
SECURITY_STRICT_DEVICE_IP = env("SECURITY_STRICT_DEVICE_IP")
SECURITY_EMAIL_ON_LOCKOUT = env("SECURITY_EMAIL_ON_LOCKOUT")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "apps.accounts.apps.AccountsConfig",
    "apps.humanizer.apps.HumanizerConfig",
    "apps.pages.apps.PagesConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.accounts.middleware.SecurityContextMiddleware",
    "apps.accounts.middleware.SuspiciousRequestMiddleware",
    "apps.accounts.middleware.CSPMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.pages.context_processors.site_branding",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Database --------------------------------------------------------------
# sqlite: zero-setup local/demo. mysql: docker-compose or PythonAnywhere.

if env("DJANGO_DB") == "mysql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": env("MYSQL_DATABASE", default="chan_humanized"),
            "USER": env("MYSQL_USER", default="chan"),
            "PASSWORD": env("MYSQL_PASSWORD", default="chan"),
            "HOST": env("MYSQL_HOST", default="127.0.0.1"),
            "PORT": str(env("MYSQL_PORT")),
            "OPTIONS": {
                "charset": "utf8mb4",
            },
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# Tests always use SQLite so they do not need Docker MySQL.
if "test" in sys.argv:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Security hardening (do not weaken before PythonAnywhere deployment) ---
if not DEBUG:
    # PythonAnywhere terminates TLS upstream; tell Django that HTTPS is in use.
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

    # Cookies only over HTTPS.
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    # HSTS: tell browsers to always use HTTPS for this domain + subdomains.
    SECURE_HSTS_SECONDS = 31_536_000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    # Additional response headers.
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
else:
    # Local development stays permissive so runserver and tests work.
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_HSTS_SECONDS = 0
    X_FRAME_OPTIONS = "DENY"

# HttpOnly session cookie is safe; CSRF cookie must stay readable for JS.
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14  # 2 weeks

# Limit the size of POST bodies (protects against huge payload abuse).
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024  # 2 MB

# Custom cache-based rate limiting is configured below (no external packages).

# Password hashing: Django already hashes by default (PBKDF2). The list is
# explicit so we never accidentally fall back to a weaker algorithm.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

# Simple in-memory cache used by the custom rate-limit decorator. On a single
# PythonAnywhere worker this is enough; for multi-worker scaling, switch to
# Memcached or Redis and point this setting there.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# Content Security Policy string. Our templates have no inline scripts, so we
# can keep a strict policy without nonces. Adjust if you add inline scripts.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "connect-src 'self'; "
    "img-src 'self' data:; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "humanizer:workspace"
LOGOUT_REDIRECT_URL = "pages:home"

# Email backend for alerts. Console backend is fine for local/PythonAnywhere demo;
# replace with a real SMTP backend before production.
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@chan-humanized-ai.local")

# --- Humanize product limits -----------------------------------------------
# Free weekly quota is shown in the UI. Pro fair-use cap is enforced in code
# but not advertised (see plan).

OPENAI_API_KEY = env("OPENAI_API_KEY", default="")
OPENAI_MODEL = env("OPENAI_MODEL")
OPENAI_TIMEOUT_SECONDS = 60

PLAN_FREE = "free"
PLAN_PRO = "pro"

FREE_WEEKLY_WORD_LIMIT = 100_000
PRO_WEEKLY_WORD_LIMIT = 1_000_000  # hidden fair-use cap
FREE_REQUEST_WORD_LIMIT = 500
PRO_REQUEST_WORD_LIMIT = 600

# Chunk size keeps each OpenAI call inside the prompt's 100-200 word sweet spot.
# Longer chunks (300-500 words) cause the model to drift back to AI-style output.
HUMANIZE_CHUNK_WORDS = 200

# Number of first-pass candidates to generate and score. Higher = more cost,
# better consistency. Set to 1 to disable candidate selection.
HUMANIZE_CANDIDATES = env.int("HUMANIZE_CANDIDATES", default=3)

# --- Logging ---------------------------------------------------------------
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": "{levelname} {asctime} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
        "security_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOGS_DIR / "security.log"),
            "maxBytes": 5 * 1024 * 1024,  # 5 MB
            "backupCount": 3,
            "formatter": "simple",
        },
    },
    "loggers": {
        "security": {
            "handlers": ["security_file", "console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["security_file", "console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
