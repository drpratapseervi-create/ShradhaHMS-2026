# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Shradha HMS — a Django 5.2 Hospital Management System for Shradha Hospital & Multispeciality Centre (Pali, Rajasthan). Single deployable Django project covering OPD/IPD patient flow, billing, lab, pharmacy inventory, OT, document management, construction/partner expense tracking, and ABDM (Ayushman Bharat Digital Mission) / ABHA health-ID integration. Deployed on Railway (see `railpack-plan.json` — apt packages for Cairo/Pango/FreeType, needed by `svglib`/`xhtml2pdf`/`pyhanko` for PDF generation).

## Environment & commands

Windows/PowerShell dev environment. Virtualenv lives at `.venv_new` — **`.venv` is broken** (its `pyvenv.cfg` points to a stale interpreter path from a different machine and fails to launch); use `.venv_new` for everything (`manage.py runserver`/`makemigrations`/`migrate`/`check`, one-off scripts, etc.) until `.venv` is fixed or replaced.

**There is no `requirements.txt` or `pyproject.toml` in the repo.** Installed packages must be inferred from `.venv_new\Lib\site-packages` or `pip freeze` — check before assuming a package is available, and if you add a new dependency, install it into `.venv_new` and tell the user there's no manifest tracking it.

**Day-to-day dev server: `manage.py runserver` (auto-reloads on file changes — the whole process restarts on save), not `waitress`.** `waitress` (`python -m waitress --port=8000 ShradhaHMS.wsgi:application`) has no autoreload at all — it silently serves pre-edit code indefinitely until manually killed and restarted, which has caused confusing "my fix isn't showing up" sessions where the server, DB, and code were all actually fine and the only problem was a long-lived waitress process nobody restarted. Only use waitress when explicitly simulating a production-style run; for normal development/testing use `runserver` instead. Even with `runserver`'s autoreload, after any code change explicitly confirm the server actually restarted (don't just assume it) — Django's `TEMPLATES[0]['OPTIONS']` doesn't set `'loaders'` here, so the template engine wraps loaders in a caching loader per-process regardless of `DEBUG`; this is harmless with `runserver` (a fresh process reloads everything) but is exactly the mechanism that makes a long-lived `waitress` process go stale.

```powershell
# activate venv + run dev server (same as the "Run Django Server" VS Code task)
.\.venv_new\Scripts\Activate.ps1; python manage.py runserver

# migrations
python manage.py makemigrations
python manage.py migrate

# create the 5 HMS role groups (Admin/Reception/Doctor/Nursing Staff/Laboratory) with baked-in permissions
python manage.py create_roles

# one-off data importers (populate ICD codes / lab investigation catalog from bundled xlsx/CSV)
python manage.py import_icd
python manage.py import_investigations

# collect static (whitenoise serves them in prod)
python manage.py collectstatic

# tests — opd/tests.py and project_expense/tests.py are still Django boilerplate (no real tests written)
python manage.py test
```

Config is via `.env` (loaded by `python-dotenv` from the repo root in `settings.py`); copy `.env.example` to `.env` for local setup. `DB_ENGINE=postgres` switches from SQLite to Postgres; a `DATABASE_URL` env var (if set) overrides both and is parsed directly.

The repo root has a number of leftover one-off scripts from past data migrations (`add_atc_codes.py`, `add_icd_codes.py`, `add_partner_models.py`, `fix_partner_deposits_final.py`, `fix_views_indent.py`, `import_icd_full_excel.py`) and stray non-project files (`25.2`, `cd`, `See`, `[57`, `db.sqlite3`, spreadsheet data files). Treat these as historical cruft, not part of the active app — don't build on them without checking with the user first.

## Architecture

### App boundaries
- **`hms`** — the actual application. Nearly everything lives here: `models.py` (~50 models, 1900+ lines), `views.py` (~3200 lines, function-based views only), `forms.py`, `urls.py` (`app_name="hms"`, mounted at `/`). Templates are organized by feature under `hms/templates/{hms,billing,documents,inventory,ipd,lab,medical,opd,ot,patients,reports,abdm}/`.
- **`opd`** — thin: no models of its own (uses `hms` models like `Appointment`/`Consultation` directly), views only render/PDF the OPD prescription (`opd_prescription`, `opd_prescription_pdf`), mounted at `/opd/`.
- **`project_expense`** — installed but currently empty (no models/views implemented); construction/partner expense tracking actually lives in `hms.models` (`ConstructionExpense`, `Vendor`, `Partner`, `PartnerDeposit`, `PartnerPayment`, `ExpenseBudget`) instead.
- **`hms.abdm`** (`hms/abdm/`) — ABDM/ABHA sub-package: `views.py` (ABHA creation/verification, HIP push/callbacks, UHI), `services/{abha,auth,hip}.py`, `utils/token_manager.py`. Note: this directory has no `__init__.py` (there's an unused `abdm__init__.py` instead) — it works as an implicit namespace package; don't assume normal package-init behavior if debugging import issues here.

### Access control
No custom user model — role is stored on `hms.UserProfile` (OneToOne to `auth.User`, auto-created via `post_save` signal), with `role` in `{admin, doctor, nursing, laboratory, reception}`. View-level authorization uses `@role_required("doctor", "admin")` from `hms/decorators.py` (superusers bypass; unauthenticated → redirect to login; wrong role → flash message + redirect to dashboard). Separately, `python manage.py create_roles` creates parallel Django `Group`/`Permission` objects — these two authorization mechanisms exist side by side and aren't unified, so check which a given view actually enforces before assuming either applies. `django-auditlog` (`AuditlogMiddleware`) is enabled globally for change tracking.

### Notable integrations
- **Encryption**: `FIELD_ENCRYPTION_KEY` (settings.py) backs `encrypted_model_fields.EncryptedCharField` for sensitive patient data (ABHA, Aadhaar, mobile) on `Patient`.
- **PDF generation**: `hms/utils.py` (`render_to_pdf`) wraps `xhtml2pdf`/`pisa` for template→PDF (prescriptions, discharge bills, receipts, reports). `hms/fonts/DejaVuSans.ttf` is bundled for non-ASCII rendering.
- **FHIR**: `hms/fhir_builder.py` builds FHIR resource bundles (Patient, OP Consultation, Discharge Summary, Lab Report) — feeds the ABDM push flow in `hms/abdm/services/hip.py`.
- **DICOM**: `hms/dicom.py` — thin wrapper for medical imaging upload/preview/study listing.
- **Admin UI**: `django-jazzmin` (must be listed before `django.contrib.admin` in `INSTALLED_APPS`) drives a themed admin; branding/menu/icon config is centralized in `JAZZMIN_SETTINGS`/`JAZZMIN_UI_TWEAKS` in `settings.py` — extend those dicts rather than fighting Jazzmin's defaults.
- **Static/media**: `whitenoise` serves static files in all environments (`CompressedManifestStaticFilesStorage`); media (patient uploads, documents, radiology) is filesystem-backed under `MEDIA_ROOT`, only served by Django itself when `DEBUG=True`.
- Claude (`ANTHROPIC_API_KEY`, `anthropic` package) is wired up for AI-assisted features referenced in urls (`ai-full-opd`, `generate-ai-medicines`, `generate-diet`) — check `hms/views.py` for the actual prompts/model calls before modifying these.

### Working in `hms/views.py`
This single file (~3200 lines) implements dashboard, patient/appointment CRUD, consultation, lab billing/results, IPD admission/discharge/vitals, OT booking, billing/receipts, inventory, document management, USG reports, and construction/partner expense views — all as plain function-based views. There's no per-feature view module split, so when adding a feature, grep for the existing section marker comments (e.g. `# ── LAB`, `# ── IPD`, `# ── BILLING`) in both `views.py` and `urls.py` to find where similar logic already lives before adding new patterns.
