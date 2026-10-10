# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Community Organizer is a generic, open-source (AGPL) Django app for organizing volunteer work. It ports the functionality of https://github.com/JumboCode/boston-community-pediatrics into something any small non-profit can self-host on a low-cost VPS. Favor a simple, stable stack that handles low traffic over adding infrastructure.

The project is at the scaffold stage: a Django 6.1 project with no apps, models, views or tests yet. `PLAN.md` holds the intended direction.

## Commands

Dependencies and Python (3.13) are managed with `uv`. Run everything through `uv run`:

- Dev server: `uv run manage.py runserver 9000` (port 8000 is taken on the dev machine)
- Migrations: `uv run manage.py makemigrations` / `uv run manage.py migrate`
- Tests: `uv run manage.py test`; for a single test, `uv run manage.py test <app>.tests.<TestCase>.<test_method>`
- Add a dependency: `uv add <package>`

No linter or formatter is configured yet.

## Layout

- `manage.py` sits at the repo root, and the Django project package is `core/` (`DJANGO_SETTINGS_MODULE=core.settings`). New Django apps go at the repo root next to `core/`.
- `core/settings.py` is still the `startproject` default: hardcoded insecure `SECRET_KEY`, `DEBUG=True`, SQLite at `db.sqlite3`, and the console email backend, configured under the Django 6.1 `MAILERS` setting rather than `EMAIL_BACKEND`.

## Planned stack (from PLAN.md, not yet implemented)

- Server-rendered Django templates, with Alpine.js for interactivity. PLAN.md lists both vanilla CSS and Bootstrap 5 with Vite for the frontend; this hasn't been settled.
- django-allauth for authentication.
- PostgreSQL in a Docker container in place of SQLite; production deployed as Docker containers via `docker-compose.yaml`.
- Caddy as the HTTP server, Thumbor for image resizing, maybe WhiteNoise.
- A transactional email SaaS (Mailchimp, SendGrid, or similar; not chosen) for delivery status and templating.
