#!/bin/sh
set -e

DB_ENGINE="${DJANGO_DB_ENGINE:-}"
if [ -z "$DB_ENGINE" ] && [ -n "${DJANGO_DB_HOST:-}" ]; then
  DB_ENGINE="django.db.backends.postgresql"
fi

if echo "$DB_ENGINE" | grep -qi "postgresql" && [ "${DJANGO_WAIT_FOR_DB:-true}" = "true" ] && [ -n "${DJANGO_DB_HOST:-}" ]; then
  until pg_isready \
    -h "$DJANGO_DB_HOST" \
    -p "${DJANGO_DB_PORT:-5432}" \
    -U "${DJANGO_DB_USER:-postgres}" \
    -d "${DJANGO_DB_NAME:-afrilux_sav}" >/dev/null 2>&1; do
    echo "Waiting for PostgreSQL at ${DJANGO_DB_HOST}:${DJANGO_DB_PORT:-5432}..."
    sleep 1
  done
fi

if [ "${DJANGO_RUN_MIGRATIONS_ON_STARTUP:-true}" = "true" ]; then
  python manage.py migrate --noinput
fi

if [ "${DJANGO_COLLECTSTATIC_ON_STARTUP:-false}" = "true" ]; then
  python manage.py collectstatic --noinput
fi

scheduler_pid=""
if [ "${DJANGO_RUN_SCHEDULER_IN_WEB:-false}" = "true" ]; then
  if [ -n "${SCHEDULER_ORGANIZATION_SLUG:-}" ]; then
    if [ "${SCHEDULER_SKIP_BACKUP:-false}" = "true" ]; then
      python manage.py run_platform_scheduler \
        --interval-seconds "${SCHEDULER_INTERVAL_SECONDS:-60}" \
        --backup-hour "${SCHEDULER_BACKUP_HOUR:-2}" \
        --backup-minute "${SCHEDULER_BACKUP_MINUTE:-0}" \
        --organization-slug "${SCHEDULER_ORGANIZATION_SLUG}" \
        --skip-backup &
    else
      python manage.py run_platform_scheduler \
        --interval-seconds "${SCHEDULER_INTERVAL_SECONDS:-60}" \
        --backup-hour "${SCHEDULER_BACKUP_HOUR:-2}" \
        --backup-minute "${SCHEDULER_BACKUP_MINUTE:-0}" \
        --organization-slug "${SCHEDULER_ORGANIZATION_SLUG}" &
    fi
  elif [ "${SCHEDULER_SKIP_BACKUP:-false}" = "true" ]; then
    python manage.py run_platform_scheduler \
      --interval-seconds "${SCHEDULER_INTERVAL_SECONDS:-60}" \
      --backup-hour "${SCHEDULER_BACKUP_HOUR:-2}" \
      --backup-minute "${SCHEDULER_BACKUP_MINUTE:-0}" \
      --skip-backup &
  else
    python manage.py run_platform_scheduler \
      --interval-seconds "${SCHEDULER_INTERVAL_SECONDS:-60}" \
      --backup-hour "${SCHEDULER_BACKUP_HOUR:-2}" \
      --backup-minute "${SCHEDULER_BACKUP_MINUTE:-0}" &
  fi
  scheduler_pid=$!
fi

if [ -z "${1:-}" ]; then
  echo "Aucune commande de demarrage fournie."
  exit 1
fi

"$@" &
main_pid=$!

shutdown() {
  if [ -n "$scheduler_pid" ]; then
    kill "$scheduler_pid" 2>/dev/null || true
  fi
  if [ -n "${main_pid:-}" ]; then
    kill "$main_pid" 2>/dev/null || true
  fi
}

trap shutdown INT TERM

if wait "$main_pid"; then
  main_status=0
else
  main_status=$?
fi

if [ -n "$scheduler_pid" ]; then
  kill "$scheduler_pid" 2>/dev/null || true
  wait "$scheduler_pid" 2>/dev/null || true
fi

exit "$main_status"
