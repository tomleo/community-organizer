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

```bash
sudo mkdir -p /opt/community-organizer && sudo chown organizer: /opt/community-organizer
cd /opt/community-organizer
curl -fsSLO https://raw.githubusercontent.com/your-org/community-organizer/main/docker-compose.yaml
curl -fsSL -o .env https://raw.githubusercontent.com/your-org/community-organizer/main/.env.production.example
curl -fsSL -o backup.env https://raw.githubusercontent.com/your-org/community-organizer/main/backup.env.example
chmod 600 .env backup.env
mkdir -p brand templates   # optional customizations; create them now so they belong to you, not root
```

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

## Updating

Read `CHANGELOG.md` for upgrade notes, then:

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
