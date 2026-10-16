# Development

## Pre-req

### Configuration

1. `cp .env.example .env`
2. Make appropriate edits per your personal configuration

### Sync django tables to postgresql

1. Start postgres: `docker compose -f docker-compose.dev.yaml up -d postgres`
2. Create the tables: `uv run manage.py migrate`

## Local-dev day-to-day 

### Basic services & django

Basically some things run in containers, mainly database (PostgreSQL) and queue infrastructure (celery worker/beat with
redis), and then the django runserver runs locally.

1. Start the database and cache services `docker compose -f docker-compose.dev.yaml up -d postgres valkey`
2. Start the frontend sass service `docker compose -f docker-compose.dev.yaml up -d frontend`
    TODO: it's just running sass?
3. Start celery workers `uv run celery -A core worker -l info --concurrency=1` (separate terminal)
4. Start celery beat `uv run celery -A core beat -l info` (separate terminal)
5. Start django server `uv run manage.py runserver 9000`

### Running tests

And to run tests, `uv run pytest`

### Email configuration

Development prints emails to the console. To see them rendered instead, run
`docker run -d -p 1025:1025 -p 8025:8025 axllent/mailpit:v1.31`, set `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`,
`EMAIL_HOST=localhost`, `EMAIL_PORT=1025` and `EMAIL_USE_TLS=false` in `.env`, and open http://localhost:8025
(MailDev works the same way). Tracking webhooks need a real provider. In production, pick a provider supported by
[anymail](https://anymail.dev) and set `EMAIL_BACKEND`, its `ANYMAIL_*` credentials, `ANYMAIL_WEBHOOK_SECRET`
and `SITE_URL`. Point the provider's tracking webhook at `https://<your site>/anymail/<provider>/tracking/`
with the webhook secret as basic auth, so bounces and spam complaints are recorded.

### Limitations of local development

- A reverse proxy (caddy) is not running locally.
- The django instance is in "debug mode". This makes development
much easier, but not safe for production.
- No SMTP server / integrations with *anymail*, see section above.

