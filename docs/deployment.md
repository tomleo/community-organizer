# Deploying Community Organizer

This guide sets up the site on a fresh Ubuntu 24.04 or Debian 13 VPS (1 vCPU and 4 GB RAM is plenty) with a
domain name you control. Expect about an hour, most of it waiting for DNS and setting up email and backups.

You need: the VPS's IP address and root SSH access, a domain (we'll use `volunteer.example.org`), an account with a
transactional email provider supported by [Anymail](https://anymail.dev) (e.g. Postmark, Mailgun, Brevo), and an
S3-compatible bucket for backups (e.g. Backblaze B2).

## 1. DNS

Create an `A` record for `volunteer.example.org` pointing at the server's IPv4 address (and an `AAAA` record for its
IPv6 address, if it has one). Check with `dig +short volunteer.example.org` before step 6; HTTPS certificates can't be
issued until it resolves.

## 2. Secure the server

Log in as root and create your own user with your SSH key:

```bash
adduser organizer
usermod -aG sudo organizer
mkdir -p /home/organizer/.ssh && cp ~/.ssh/authorized_keys /home/organizer/.ssh/
chown -R organizer:organizer /home/organizer/.ssh
```

Log in again as `organizer` in a new terminal to make sure it works, then turn off password and root logins in
`/etc/ssh/sshd_config` (`PasswordAuthentication no`, `PermitRootLogin no`) and `sudo systemctl restart ssh`.

Firewall, automatic security updates and a swap file:

```bash
sudo apt update && sudo apt install -y ufw unattended-upgrades
sudo ufw allow OpenSSH && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw allow 443/udp
sudo ufw enable
sudo dpkg-reconfigure -plow unattended-upgrades
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## 3. Install Docker

Follow Docker's instructions for your distribution ("Install using the apt repository"):
<https://docs.docker.com/engine/install/ubuntu/> or <https://docs.docker.com/engine/install/debian/>. Then let your
user run it: `sudo usermod -aG docker organizer`, and log out and back in. `docker compose version` should print
v2.24 or newer.

## 4. Get the compose file

The app itself comes from the image (`ghcr.io/tomleo/community-organizer`), which `docker compose` pulls in step 7.
What you download here are the files that live next to it on the server: the compose file and the two settings
templates. Take them from the release you'll run, so they match the image (the newest version is the top
[tag](https://github.com/tomleo/community-organizer/tags) and the top entry in `CHANGELOG.md`):

```bash
sudo mkdir -p /opt/community-organizer && sudo chown organizer: /opt/community-organizer
cd /opt/community-organizer
RELEASE=v0.1.0
SRC=https://raw.githubusercontent.com/tomleo/community-organizer/$RELEASE
curl -fsSLO $SRC/docker-compose.yaml
curl -fsSL -o .env $SRC/.env.production.example
curl -fsSL -o backup.env $SRC/backup.env.example
chmod 600 .env backup.env
mkdir -p brand templates   # optional customizations; create them now so they belong to you, not root
```

If a tunnel or proxy such as Pangolin handles HTTPS for this server, see
[Behind a tunnel or reverse proxy](#behind-a-tunnel-or-reverse-proxy-pangolin-cloudflare-tunnel) first.

`VERSION` in `.env` then picks which images to run (the comment above it explains the choices). To try
unreleased changes (e.g. on a demo site), use `RELEASE=main` and `VERSION=main`, or `VERSION=sha-<commit>` to stay on
one build.

## 5. Configure `.env`

Open `.env` and fill in every value in the Required section. Generate secrets with `openssl rand -hex 32` (once for
`SECRET_KEY`, once for `POSTGRES_PASSWORD`, and once for `RESTIC_PASSWORD` in `backup.env`). Backup settings live in
`backup.env` because only the backup service should hold credentials that can delete backups.

**Save `RESTIC_PASSWORD` in your organization's password manager now.** Backups are encrypted with it; if the server
is lost and you don't have the password, the backups can't be read.

While you're first setting up, set `SECURE_HSTS_SECONDS=3600` so a mistake with HTTPS doesn't lock browsers out for
a year; remove it once the site works.

## 6. Email

The site won't start without a working email setup (volunteers can't verify their accounts otherwise).

In your email provider, verify the sending domain (it gives you DNS records to add) and create an API token; put it
in `.env` (see the Anymail docs for your provider's variable names). Set `ANYMAIL_WEBHOOK_SECRET` to
`someuser:a-long-random-password`. Once the site is running (next step), add a delivery-tracking webhook in the
provider pointing at `https://someuser:a-long-random-password@volunteer.example.org/anymail/<provider>/tracking/`
(e.g. `postmark`), and sign up as a test volunteer to check the verification email arrives.

### Choosing a provider

Any provider Anymail supports works. Free tiers as of October 2026 (they change often; check the provider's pricing
page before signing up):

| Provider | Free tier (emails) | First paid plan | Notes |
|---|---|---|---|
| Brevo | ~300/day (~9,000/month) | ~$9–15/month | Largest ongoing free tier; EU-based |
| Mailjet | ~6,000/month (~200/day) | ~$15/month | |
| Resend | 3,000/month (100/day) | $20/month for 50,000 | |
| Mailgun | ~100/day | ~$15/month for 10,000 | |
| Postmark | 100/month | ~$15/month for 10,000 | Strong deliverability; the free tier is for testing only |
| Amazon SES | None; new AWS accounts get general AWS credit | $0.10 per 1,000 emails, no monthly fee | Cheapest at volume (10,000 emails ≈ $1); you must request removal from sandbox mode |
| Mailtrap | Small free tier, plus a test inbox | Low-cost tiers | Test inbox catches mail without delivering it |
| SendGrid | Trial only | ~$20/month | Anymail no longer tests it |

Non-profit programs (also October 2026; confirm eligibility with the provider):

- **Amazon SES:** through [TechSoup](https://www.techsoup.org/amazon-web-services), US non-profits with budgets
  under $10 million can get $1,000 of AWS credit a year for a $95 admin fee. That pays for about 10 million emails.
- **Mailjet:** 20% off the monthly subscription (not annual plans) after you send proof of non-profit status to
  support.
- **Brevo:** 15% off the Enterprise plan only, arranged through their sales team.
- **Resend, Postmark, Mailgun:** no published non-profit discount.

A small organization usually stays within Brevo's or Mailjet's free tier. Every provider asks you to add SPF and
DKIM DNS records for the sending domain.

### Demo or staging sites

A public demo with open sign-up lets anyone make the site email addresses they don't own, which hurts your
sending reputation and can get a provider account suspended. Instead, catch all mail with
[Mailpit](https://mailpit.axllent.org/) so nothing is delivered. Create `docker-compose.override.yaml` next to
`docker-compose.yaml`:

```yaml
services:
  mailpit:
    image: axllent/mailpit:v1.31
    restart: unless-stopped
    ports:
      - "127.0.0.1:8025:8025"  # web UI, reachable only from the server itself
```

and in `.env` use SMTP instead of Anymail (no `ANYMAIL_*` variables or webhook needed):

```
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=mailpit
EMAIL_PORT=1025
EMAIL_USE_TLS=false
```

Run `docker compose up -d`, then read the caught mail through an SSH tunnel: `ssh -L 8025:localhost:8025
you@server` and open http://localhost:8025. Don't publish the Mailpit UI on the internet: anyone who can read it can
read password-reset links and take over accounts, including the admin's.

## 7. Start the site

```bash
docker compose up -d
docker compose ps
```

`setup` should show "exited (0)" and the other services "running" (`web` "healthy"). If `setup` failed, see
`docker compose logs setup`. Visit `https://volunteer.example.org/health/`; it should say `"status": "ok"`.

Create the first admin and log in through the normal login page:

```bash
docker compose run --rm web manage createsuperuser
```

Then open Manage → Site settings: set the organization name, time zone and contact email.

## 8. Backups

Create a private bucket and an application key limited to it, and put the repository and key in `backup.env`
(uncomment `RESTIC_REPOSITORY`). Then:

```bash
docker compose up -d
docker compose run --rm backup backup-now
docker compose run --rm backup snapshots
```

Backups then run nightly at `BACKUP_TIME` in the site's time zone. On Sundays the backup service also checks the
repository and test-restores the database into a temporary database. Manage → Site settings shows when the last
backup succeeded, and `ADMINS` get an email if one fails.

**Practice a restore** before you need one (do this before real volunteers sign up):

```bash
docker compose stop web worker beat
docker compose run --rm backup restore latest
docker compose up -d
```

The restore asks you to type the domain, then replaces the database and uploaded files with the snapshot's.

## 9. Optional extras

- **Uptime monitoring:** point a free monitor (e.g. UptimeRobot, Uptime Kuma) at `https://volunteer.example.org/health/`.
- **Sentry or GlitchTip:** set `SENTRY_DSN` in `.env` and `docker compose up -d`. Personal data isn't sent.
- **Colors and fonts:** create `brand/_brand.scss` next to `docker-compose.yaml` (see `frontend/src/_brand.scss` in
  the repository for the variables), then `docker compose up -d`. Startup stops if the colors fail the contrast
  check; `docker compose logs setup` says why.
- **Template and email overrides:** put files in `templates/` next to `docker-compose.yaml` with the same relative
  path as the app's templates (e.g. `templates/emails/reminder/body.txt`), then `docker compose up -d`. Web pages,
  workers and the scheduler all read them.

## Behind a tunnel or reverse proxy (Pangolin, Cloudflare Tunnel)

If the server isn't reachable from the internet and a tunnel or proxy handles HTTPS for it, add
[`docker-compose.tunnel.yaml`](../docker-compose.tunnel.yaml) on top of the stock compose file. With it, Caddy serves
plain HTTP on one port and keeps the proxy's `X-Forwarded-Proto` and `X-Forwarded-For` headers. Skip opening ports
80 and 443 in step 2, and in step 4 also download it:

```bash
curl -fsSLO $SRC/docker-compose.tunnel.yaml
```

Then in `.env`:

```
# Load both files for every docker compose command.
COMPOSE_FILE=docker-compose.yaml:docker-compose.tunnel.yaml
# The public address, as visitors see it; the allowed host name and trusted origin for forms come from it.
SITE_URL=https://volunteer.example.org
# The port the proxy connects to on this server (default 8080).
HTTP_PORT=4539
```

Point the proxy at `http://<server address>:4539`. It must pass the original `Host` header on (Pangolin and
Cloudflare Tunnel do by default).

- **Trusted proxies:** Caddy trusts forwarded headers from any private address. Anyone else on the LAN who can
  reach the port could fake them, so if you know the proxy's address, put it in place of `private_ranges` in
  `docker-compose.tunnel.yaml`.
- **Visitor addresses:** the proxy and Caddy each add an `X-Forwarded-For` entry, so the override sets
  `TRUSTED_PROXY_COUNT=2` for login rate limits. Change it in `.env` if your chain has more hops.
- **Other host names:** to also answer on another name (e.g. the server's LAN address), set `ALLOWED_HOSTS` and
  `CSRF_TRUSTED_ORIGINS` in `.env`, comma-separated and including the public ones.

## Updating

Read `CHANGELOG.md` for upgrade notes. If a release changes `docker-compose.yaml` (or `docker-compose.tunnel.yaml`),
the notes say so; download it again with the new `RELEASE` as in step 4. Then:

```bash
cd /opt/community-organizer
docker compose pull
docker compose up -d
docker image prune -f
```

`setup` applies database migrations before the new version starts. The site is unavailable for a few seconds.

## Moving to a new server

Set up the new server through step 6 with the same `.env` and `backup.env` (including `RESTIC_PASSWORD`), then instead of creating an
admin:

```bash
docker compose up -d postgres valkey
docker compose run --rm backup restore latest
docker compose up -d
```

Point DNS at the new server; Caddy gets a new certificate once it resolves.

## Useful commands

| Task | Command |
|---|---|
| Logs | `docker compose logs -f web` (or `worker`, `beat`, `backup`, `caddy`) |
| Django shell | `docker compose run --rm web manage shell` |
| Restart everything | `docker compose up -d --force-recreate` |
| Disk usage | `docker system df` |
