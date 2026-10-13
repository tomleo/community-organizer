# Community Organizer

A simple application for organizing volunteer work

## Development

1. `cp .env.example .env`
2. `docker compose -f docker-compose.dev.yaml up -d postgres valkey`
3. `uv run manage.py migrate`
4. `docker compose -f docker-compose.dev.yaml up -d frontend`
5. `uv run celery -A core worker -l info --concurrency=1` (separate terminal)
6. `uv run celery -A core beat -l info` (separate terminal)
7. `uv run manage.py runserver 9000` (port 8000, the default, is taken)

Tests: `uv run pytest`

## Email

Development prints emails to the console. In production, pick a provider supported by
[anymail](https://anymail.dev) and set `EMAIL_BACKEND`, its `ANYMAIL_*` credentials, `ANYMAIL_WEBHOOK_SECRET`
and `SITE_URL`. Point the provider's tracking webhook at `https://<your site>/anymail/<provider>/tracking/`
with the webhook secret as basic auth, so bounces and spam complaints are recorded.

## Customizing

- **Content** (no code): Admins set the home page headline, intro, images, About section and footer note on
  Manage → Site settings, and the yes/no questions volunteers answer on Manage → Profile questions.
- **Colors and fonts**: edit `frontend/src/_brand.scss` (Bootstrap Sass variables), rebuild the frontend, then run
  `uv run manage.py check_brand_contrast`. It fails if the primary or link color is below WCAG AA (4.5:1) on white.
  Colors are deliberately not editable in the admin, so contrast stays a reviewed, technical change.
- **Templates and emails**: set `CUSTOM_TEMPLATES_DIR` to a directory; any file there with the same relative path as
  one of the app's templates (e.g. `home.html`, `emails/reminder/body.txt`) replaces it.

## Deploying

Production runs from one `docker-compose.yaml` (Caddy with automatic HTTPS, the app, Celery, PostgreSQL, Valkey and
nightly restic backups). See [docs/deployment.md](docs/deployment.md) for a step-by-step guide and
[docs/releasing.md](docs/releasing.md) for building release images.

## Architecture

The architecture is build around running the whole application under a low-cost VPS instance. The advantages of this
approach are:

1. Predictable low monthly costs; hostinger's KVM1 instance for example is aroun $6.49 a month.
2. No vendor-lockin; there's free-tier options with services like AWS but getting a robust database, task scheduling,
   authentication, and frontend without any cold-starts is probably not possible. Aurora is probably overkill for a
   small non-profit. Cognito difficult to configure well and complicated to migrate out of. Event-driven offerings like
   Lamdas and API Gateway are pretty good, but do suffer from cold-starts for low-traffic non-profits. Provisioned
   concurency for serverless infrastructure can become expensive and without proper WAF and billing protection could
   result in high costs for spikey traffic (see first point)
3. Open-source; there's some companies that can handle community organizing and volunterring well, but for a price.
   HubSpot's "drip-campaign" logic is fantastic but expensive (see first point). Also building everything within
   HubSpot leaves a non-profit vulnerable to price changes (see 2nd point)
4. You probably don't need "limitless scale", and if you do then low monthly cost is likely out of the question. If you
   have high-volume and a large budget then *enterprise* offerings are probably a better fit.

## Tech-stack

Everything runs in docker containers can be kicked off via docker-compose.

- HTTP server via [caddy](https://github.com/caddyserver/caddy)
- Application code via [django](https://www.djangoproject.com/)
    - authentication via django-allauth
    - image optimization via pillow
    - Interops with IaaS/SaaS email providers via [Anymail](https://anymail.dev)
- Frontend styling via [bootstrap 5](https://getbootstrap.com/docs/5.3/getting-started/vite/)
    - richtext editing via Trix
- Database via PostgreSQL
- Asynchronous and scheduled processes via celery (backed by ValKey)
- Backups via Restic
- Monitoring via Sentry (optional)

