# syntax=docker/dockerfile:1

FROM node:24-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN mkdir -p /app/static && npm run build

FROM python:3.13-slim-trixie AS app
ARG TARGETARCH
ARG APP_VERSION=dev
ARG RESTIC_VERSION=0.18.1
ARG SASS_VERSION=1.105.1
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH=/opt/venv/bin:/opt/dart-sass:$PATH \
    APP_VERSION=$APP_VERSION \
    MEDIA_ROOT=/app/media \
    STATIC_ROOT=/app/staticfiles \
    BACKUP_WORK_DIR=/tmp/organizer-backup

# PostgreSQL 18 client tools (pg_dump, pg_restore, psql), restic and dart-sass.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl bzip2 \
 && install -d /usr/share/postgresql-common/pgdg \
 && curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc \
 && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt trixie-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client-18 \
 && case "$TARGETARCH" in amd64) SASS_ARCH=x64 ;; arm64) SASS_ARCH=arm64 ;; *) echo "Unsupported architecture $TARGETARCH" >&2; exit 1 ;; esac \
 && cd /tmp \
 && curl -fsSLO "https://github.com/restic/restic/releases/download/v${RESTIC_VERSION}/restic_${RESTIC_VERSION}_linux_${TARGETARCH}.bz2" \
 && curl -fsSLO "https://github.com/restic/restic/releases/download/v${RESTIC_VERSION}/SHA256SUMS" \
 && grep " restic_${RESTIC_VERSION}_linux_${TARGETARCH}.bz2\$" SHA256SUMS | sha256sum -c - \
 && bunzip2 -c "restic_${RESTIC_VERSION}_linux_${TARGETARCH}.bz2" > /usr/local/bin/restic \
 && chmod +x /usr/local/bin/restic \
 && curl -fsSL "https://github.com/sass/dart-sass/releases/download/${SASS_VERSION}/dart-sass-${SASS_VERSION}-linux-${SASS_ARCH}.tar.gz" \
      | tar -xz -C /opt \
 && rm -f /tmp/restic_* /tmp/SHA256SUMS \
 && apt-get purge -y curl bzip2 \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
COPY --from=frontend /app/static/dist static/dist
# Pristine stock CSS: compile_brand starts from it on every setup run.
COPY --from=frontend /app/static/dist/main.css frontend/stock/main.css
COPY --from=frontend /app/frontend/node_modules/bootstrap/scss frontend/node_modules/bootstrap/scss
RUN useradd --uid 1000 --create-home app \
 && mkdir -p media staticfiles \
 && chown -R app:app /app
USER app
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["web"]
