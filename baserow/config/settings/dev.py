from .base import *  # noqa: F403, F401
import snoop

SECRET_KEY = os.getenv("SECRET_KEY", "dev_hardcoded_secret_key")  # noqa: F405

DEBUG = True
WEBHOOKS_MAX_CONSECUTIVE_TRIGGER_FAILURES = 4
WEBHOOKS_MAX_RETRIES_PER_CALL = 4

INSTALLED_APPS += ["django_extensions", "silk"]  # noqa: F405

MIDDLEWARE += [  # noqa: F405
    "silk.middleware.SilkyMiddleware",
]

SILKY_ANALYZE_QUERIES = True

snoop.install()

CELERY_EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_USE_TLS = False
EMAIL_HOST = "mailhog"
EMAIL_PORT = 1025

try:
    from .local import *  # noqa: F403, F401
except ImportError:
    pass
