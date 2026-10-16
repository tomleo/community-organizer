# Community Organizer

A simple application for organizing volunteer work

## Configuration

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
   small non-profit. Cognito is difficult to configure well and complicated to migrate out of. Event-driven offerings like
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

