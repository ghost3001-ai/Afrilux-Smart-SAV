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

exec "$@"
