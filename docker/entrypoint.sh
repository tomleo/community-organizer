#!/bin/sh
# One image, many roles: docker compose passes the role as the command.
set -eu

role="${1:-web}"
[ "$#" -gt 0 ] && shift

case "$role" in
  web)
    # Only Caddy can reach this port, so trust its X-Forwarded-* headers.
    exec gunicorn core.wsgi --bind 0.0.0.0:8000 --workers "${WEB_WORKERS:-3}" --timeout 30 \
      --max-requests 1000 --max-requests-jitter 100 --forwarded-allow-ips '*' --access-logfile - "$@" ;;
  worker)
    exec celery -A core worker -l info --concurrency=1 "$@" ;;
  beat)
    exec celery -A core beat -l info --schedule /tmp/celerybeat-schedule "$@" ;;
  setup)
    python manage.py migrate --noinput
    python manage.py compile_brand
    # Check before collecting: the running site serves whatever lands in the static volume.
    python manage.py check_brand_contrast
    python manage.py collectstatic --noinput --verbosity 0
    exec python manage.py check --deploy --fail-level WARNING ;;
  backup)
    exec python manage.py run_backups ;;
  backup-now)
    exec python manage.py backup_now ;;
  snapshots)
    exec restic snapshots "$@" ;;
  restore)
    exec python manage.py restore_backup "$@" ;;
  healthcheck)
    exec python /app/docker/healthcheck.py ;;
  manage)
    exec python manage.py "$@" ;;
  *)
    exec "$role" "$@" ;;
esac
