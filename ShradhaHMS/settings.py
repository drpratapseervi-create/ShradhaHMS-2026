# ShradhaHMS/settings.py
from pathlib import Path
import os
from urllib.parse import urlparse

# optional: local .env loader
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except Exception:
    pass

# ── BASE DIR ───────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

# ── CORE ───────────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'change-me-in-dev')
DEBUG      = os.getenv('DEBUG', 'True').lower() in ('1', 'true', 'yes')
ALLOWED_HOSTS = ["*"]

# ── APPS ───────────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'jazzmin',                              # ← must be FIRST before admin
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # project apps
    'hms',
    'opd',
    'project_expense',
    'auditlog',
]

# ── MIDDLEWARE ─────────────────────────────────────────────────────────────
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'auditlog.middleware.AuditlogMiddleware',
]

ROOT_URLCONF      = 'ShradhaHMS.urls'
WSGI_APPLICATION  = 'ShradhaHMS.wsgi.application'

# ── TEMPLATES ──────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR / 'templates',
            BASE_DIR / 'hms' / 'templates',
            BASE_DIR / 'opd' / 'templates',
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# ── DATABASE ───────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv('DATABASE_URL', '').strip()
if DATABASE_URL:
    parsed = urlparse(DATABASE_URL)
    scheme = parsed.scheme or ''
    if scheme.startswith('postgres'):
        ENGINE = 'django.db.backends.postgresql'
    elif scheme.startswith('mysql'):
        ENGINE = 'django.db.backends.mysql'
    else:
        ENGINE = 'django.db.backends.sqlite3'

    DATABASES = {
        'default': {
            'ENGINE':   ENGINE,
            'NAME':     (parsed.path or '').lstrip('/') or os.getenv('DB_NAME', 'shradha_hms'),
            'USER':     parsed.username or os.getenv('DB_USER', ''),
            'PASSWORD': parsed.password or os.getenv('DB_PASSWORD', ''),
            'HOST':     parsed.hostname or os.getenv('DB_HOST', '127.0.0.1'),
            'PORT':     parsed.port     or os.getenv('DB_PORT', ''),
        }
    }
else:
    if os.getenv('DB_ENGINE', 'sqlite').lower().startswith('post'):
        DATABASES = {
            'default': {
                'ENGINE':   'django.db.backends.postgresql',
                'NAME':     os.getenv('DB_NAME', 'shradha_hms'),
                'USER':     os.getenv('DB_USER', 'postgres'),
                'PASSWORD': os.getenv('DB_PASSWORD', ''),
                'HOST':     os.getenv('DB_HOST', '127.0.0.1'),
                'PORT':     os.getenv('DB_PORT', '5432'),
            }
        }
    else:
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME':   BASE_DIR / 'db.sqlite3',
            }
        }

# ── I18N / TIME ────────────────────────────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE     = os.getenv('TIME_ZONE', 'Asia/Kolkata')
USE_I18N      = True
USE_TZ        = True
USE_L10N      = False
DATE_FORMAT   = "d-m-Y"
TIME_FORMAT   = "H:i"

# ── STATIC / MEDIA ─────────────────────────────────────────────────────────
STATIC_URL   = '/static/'
STATIC_ROOT  = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    p for p in [
        BASE_DIR / 'static',
        BASE_DIR / 'ShradhaHMS' / 'static',
    ] if p.exists()
]
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL  = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ── AUTH ───────────────────────────────────────────────────────────────────
LOGIN_URL           = '/login/'
LOGIN_REDIRECT_URL  = '/dashboard/'
LOGOUT_REDIRECT_URL = '/login/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── SECURITY (production only) ─────────────────────────────────────────────
if not DEBUG:
    SECURE_PROXY_SSL_HEADER      = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE        = True
    CSRF_COOKIE_SECURE           = True
    SECURE_SSL_REDIRECT          = os.getenv('SECURE_SSL_REDIRECT', 'True').lower() in ('1', 'true', 'yes')
    SECURE_HSTS_SECONDS          = int(os.getenv('SECURE_HSTS_SECONDS', '2592000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD          = True
    X_FRAME_OPTIONS              = 'DENY'

# ── LOGGING ────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv('DJANGO_LOG_LEVEL', 'INFO')
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root':     {'handlers': ['console'], 'level': LOG_LEVEL},
}

# ══════════════════════════════════════════════════════════════════════════
#  JAZZMIN — Modern Admin UI
# ══════════════════════════════════════════════════════════════════════════
JAZZMIN_SETTINGS = {
    # ── Branding ──────────────────────────────────────────────────────────
    "site_title":    "Shradha HMS",
    "site_header":   "Shradha Hospital",
    "site_brand":    "Shradha HMS",
    "welcome_sign":  "Welcome to Shradha Hospital Management System",
    "copyright":     "Shradha Hospital & Multispeciality Centre, Pali (Raj.)",

    # Uncomment & place logo at static/img/logo.png to enable:
    # "site_logo": "img/logo.png",
    # "login_logo": "img/logo.png",

    # ── Top navigation ────────────────────────────────────────────────────
    "topmenu_links": [
        {"name": "Home",         "url": "admin:index",  "permissions": ["auth.view_user"]},
        {"name": "HMS Portal",   "url": "/dashboard/",  "new_window": False},
        {"name": "OPD",          "url": "/opd/",        "new_window": False},
        {"name": "Lab Billing",  "url": "/lab/billing/","new_window": False},
    ],

    # ── User menu (top-right) ─────────────────────────────────────────────
    "usermenu_links": [
        {"name": "HMS Dashboard", "url": "/dashboard/", "icon": "fas fa-th-large"},
        {"name": "My Profile",    "url": "/admin/auth/user/", "icon": "fas fa-user"},
    ],

    # ── Sidebar icons (Font Awesome 5) ────────────────────────────────────
    "icons": {
        # Auth
        "auth":                      "fas fa-users-cog",
        "auth.user":                 "fas fa-user",
        "auth.Group":                "fas fa-users",

        # HMS core
        "hms.Patient":               "fas fa-procedures",
        "hms.UserProfile":           "fas fa-id-badge",
        "hms.Doctor":                "fas fa-user-md",
        "hms.Department":            "fas fa-hospital",
        "hms.Appointment":           "fas fa-calendar-check",
        "hms.Bed":                   "fas fa-bed",

        # Lab
        "hms.Investigation":         "fas fa-flask",
        "hms.InvestigationCategory": "fas fa-tags",
        "hms.InvestigationParameter":"fas fa-sliders-h",
        "hms.InvestigationResult":   "fas fa-vial",

        # Billing
        "hms.ProcedureItem":         "fas fa-syringe",
        "hms.ProcedureBill":         "fas fa-file-invoice-dollar",
        "hms.BillItem":              "fas fa-receipt",
        "hms.Consultation":          "fas fa-stethoscope",
        "hms.DischargebBill":        "fas fa-sign-out-alt",

        # Pharmacy
        "hms.DrugMaster":            "fas fa-pills",
    },
    "default_icon_parents":  "fas fa-chevron-circle-right",
    "default_icon_children": "fas fa-circle",

    # ── Sidebar ordering ──────────────────────────────────────────────────
    "order_with_respect_to": [
        "auth",
        "hms",
        "hms.Patient",
        "hms.Doctor",
        "hms.Department",
        "hms.Appointment",
        "hms.Bed",
        "hms.Investigation",
        "hms.ProcedureBill",
        "hms.DischargebBill",
        "hms.DrugMaster",
    ],

    # ── Behaviour ─────────────────────────────────────────────────────────
    "show_sidebar":           True,
    "navigation_expanded":    True,
    "hide_apps":              [],
    "hide_models":            [],
    "related_modal_active":   True,      # popup for related fields
    "search_model":           ["auth.user", "hms.Patient"],
    "changeform_format":      "horizontal_tabs",
    "changeform_format_overrides": {
        "auth.user":  "collapsible",
        "auth.group": "vertical_tabs",
    },
}

JAZZMIN_UI_TWEAKS = {
    "navbar_small_text": False,
    "footer_small_text": False,
    "body_small_text": False,
    "brand_small_text": False,

    # ── Colors ────────────────────────────────────────────────────────────
    "brand_colour": "navbar-success",
    "accent": "accent-teal",
    "navbar": "navbar-dark",
    "no_navbar_border": False,
    "sidebar": "sidebar-dark-success",

    # ── Layout ────────────────────────────────────────────────────────────
    "navbar_fixed": True,
    "sidebar_fixed": True,
    "layout_boxed": False,
    "footer_fixed": False,

    # ── Sidebar nav style ─────────────────────────────────────────────────
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": True,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": False,

    # ── Theme ─────────────────────────────────────────────────────────────
    "theme": "default",
    "dark_mode_theme": None,

    # ── Button classes (MUST be inside Jazzmin) ──────────────────────────
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success",
    },

# ── Actions ──────────────────────────────────────────────────────────
    "actions_sticky_top": True,
}
# ══════════════════════════════════════════════════════════════════════════
#  ABDM (Ayushman Bharat Digital Mission) Configuration
# ══════════════════════════════════════════════════════════════════════════
ABDM_BASE_URL      = os.getenv("ABDM_BASE_URL",      "https://sandbox.abdm.gov.in/api")
ABDM_CLIENT_ID     = os.getenv("ABDM_CLIENT_ID",     "")
ABDM_CLIENT_SECRET = os.getenv("ABDM_CLIENT_SECRET", "")
ABDM_TOKEN_URL     = os.getenv("ABDM_TOKEN_URL",     "https://dev.abdm.gov.in/gateway/v0.5/sessions")
ABDM_HIP_ID        = os.getenv("ABDM_HIP_ID",        "")

# ✅ ADD THIS:
# ══════════════════════════════════════════════════════════════════════════
#  ENCRYPTION — Sensitive patient fields (ABHA, Aadhaar, mobile)
# ══════════════════════════════════════════════════════════════════════════
FIELD_ENCRYPTION_KEY = os.getenv(
    "FIELD_ENCRYPTION_KEY",
    "lYVCcXXT4gu2HtCOJlBOw81SjA783BHHlmyB6qX1TRU="
)

# ── ANTHROPIC (Claude) ──────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')
# Explicit on/off switch for the AI Clinical Assist / AI Suggest Medicines /
# AI diet chart features, independent of whether a key is present — lets you
# hold a key in .env without the app trying to call a not-yet-funded account.
AI_FEATURES_ENABLED = os.getenv('AI_FEATURES_ENABLED', 'False').lower() in ('1', 'true', 'yes')