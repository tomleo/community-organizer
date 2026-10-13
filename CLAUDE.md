# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Community Organizer is a generic, open-source (AGPL) Django app for organizing volunteer work. It ports the functionality of https://github.com/JumboCode/boston-community-pediatrics into something any small non-profit can self-host on a low-cost VPS (target: 1 vCPU, 4 GB RAM). Favor a simple, stable stack that handles low traffic over adding infrastructure.

Parts 1–7 (foundation, events, registration, notifications, admin tools, customization, deployment) are implemented; see `docs/superpowers/specs/` for the roadmap and `docs/superpowers/plans/` for implementation plans.

## Commands

Python tooling runs through `uv run`; Node runs only in Docker (the host's Node is too old for Vite 8).

- First-time setup: `cp .env.example .env` (adjust `POSTGRES_PORT`/`DATABASE_URL` if 5432 is taken), then `docker compose -f docker-compose.dev.yaml up -d postgres valkey`, then `uv run manage.py migrate`
- Dev server: `uv run manage.py runserver 9000` (port 8000 is taken on the dev machine)
- Celery worker: `uv run celery -A core worker -l info --concurrency=1`
- Celery beat (expires waitlist offers every 5 minutes): `uv run celery -A core beat -l info`
- Frontend: `docker compose -f docker-compose.dev.yaml up frontend` (runs `vite build --watch` into `static/dist/`; no hot reload, refresh the page)
- Tests (need Postgres and Valkey running): `uv run pytest`; single test: `uv run pytest tests/accounts/test_onboarding.py::test_exempt_paths`
- Lint/format: `uv run ruff check .` / `uv run ruff format .`
- First admin: `uv run manage.py createsuperuser`, then log in through the normal login page
- Production-like stack locally: `docker build -t community-organizer:local .` then `docker compose --env-file docker/local.env -f docker-compose.yaml -f docker-compose.local.yaml up -d` (https://localhost:8443; project name `organizer-local`)
- Release: `IMAGE=… scripts/release.sh <version>` (docs/releasing.md)

## Layout

- `core/`: project package and installed app. Settings read env vars via `core/env.py` (and `.env`). Shared Celery tasks (`send_email`, `resize_image`) and image helpers live here.
- `organization/`: `SiteSettings` singleton (`SiteSettings.load()`, cached in Valkey), Coordinator/Admin groups, `MANAGEMENT_LINKS` (the navbar Manage menu, each entry gated by a permission), site time zone middleware.
- `accounts/`: `Profile` (one-to-one with stock `auth.User`; all fields optional in the DB, required-ness from `SiteSettings` via `accounts/requirements.py`), allauth adapter, onboarding middleware.
- `events/`: `Location`, `Event`, `Position`, `EventPhoto`. Event dates come from positions via `Event.objects.with_dates()`; all visibility rules live in `events/querysets.py`. Status changes go through `Event.publish()/cancel()/reinstate()/archive()/restore()`, which raise `EventStateError`. Public views in `events/views.py`, staff views in `events/manage.py`; event pages emit schema.org JSON-LD (`events/jsonld.py`).
- `registrations/`: `Registration` (one row per party per position; status registered/waitlisted/offered/cancelled/removed/expired) and `Guest`. All rules live in `registrations/services.py` — always go through it, never change `Registration.status` directly in views. It locks the position row (`select_for_update`) and raises `RegistrationError` with a user-facing message. Spots taken are computed from registrations, never stored.
- `notifications/`: `OutgoingEmail` is both the outbox and the delivery log. Emails are rendered from `templates/emails/<kind>/` by helpers in `notifications/messages.py`, created inside the triggering transaction by `notifications.outbox.queue()`, and sent after commit by a Celery task; beat re-sends stuck rows, sends reminders hourly and the staff digest at 07:00 site time. Anymail tracking webhooks (`/anymail/<provider>/tracking/`) update statuses and flag undeliverable addresses (`Profile.email_undeliverable_at`). New email kinds: add an `OutgoingEmail.Kind`, a helper in `messages.py`, and the three templates.
- Email provider: set `EMAIL_BACKEND` to an anymail backend and `ANYMAIL_*` env vars (copied into `ANYMAIL` automatically). `SITE_URL` must be set in production for links in emails.
- `volunteers/`: staff directory, volunteer pages, role changes, CSV exports and `anonymize()`. Hours are computed by `volunteer_stats()` (attended registrations only), never stored. Deleting an account anonymizes it — personal data erased, registrations kept — and users with `profile.deleted_at` are never emailed. Group messages (`notifications.Message`, `notifications/group.py`) go through the outbox one email per recipient; the announcement opt-out applies to directory selections only.
- Organization-defined yes/no questions: `accounts.ProfileQuestion`; answers are JSON maps (`{"<question id>": bool}`) on `Profile.answers` and `Guest.answers`, read and written through `accounts/questions.py`. Home page and footer text/images are `SiteSettings` fields. Look and wording are customized in code: `frontend/src/_brand.scss`, `CUSTOM_TEMPLATES_DIR`, `manage.py check_brand_contrast`; there are no color settings in the admin.
- Deployment: one image, roles chosen by `docker/entrypoint.sh` (`web`, `worker`, `beat`, `setup`, `backup`, …); `setup` migrates, compiles `brand/_brand.scss` (`compile_brand`), checks contrast, collects static and runs deploy checks before anything else starts. `/health/` is answered by `core.middleware.HealthCheckMiddleware` before other middleware. Backups (`core/backups.py`) shell out to `pg_dump`/`restic`; tests replace them with stubs from `tests/backup_stubs.py` (`backup_tools` fixture). Production refuses the console email backend (`check --deploy`).
- CSV downloads go through `volunteers.csv_export.csv_response()`, which escapes spreadsheet formulas.
- Rich text uses `core.fields.RichTextField` (Trix editor, nh3 sanitizing on save) and must be rendered with `{{ value|rich_text }}` (`{% load richtext_tags %}`), never `|safe`.
- Staff templates extend `templates/manage/base.html`, which loads the `manage` Vite entry (Trix). Public pages don't load Trix.
- Code checks permissions, never group names. New staff areas add a `MANAGEMENT_LINKS` entry and grant permissions to groups in a data migration.
- Email settings use Django 6.1's `MAILERS`, not `EMAIL_BACKEND`.
- Valkey DB 0 is the Celery broker, DB 1 the cache (`cache.clear()` flushes a whole DB).
- Forms rendered inside `class="app-form"` get Bootstrap styling from `frontend/src/main.scss`; no per-widget CSS classes needed.
- Tests live in `tests/` (pytest, importlib mode); shared values go in `tests/constants.py`, never import `conftest`.

## Stack

Django templates with Bootstrap 5 (Sass, built by Vite) and Bootstrap's own JS; Trix rich text (staff pages only) sanitized with nh3; django-allauth (email + optional Google); Postgres; Celery with Valkey; Pillow resizing at upload time (no Thumbor). Production is docker compose with Caddy serving static and media files (docs/deployment.md).
