#!/bin/sh
set -e

PORT_VALUE="${PORT:-8000}"
WORKERS_VALUE="${GUNICORN_WORKERS:-${WEB_CONCURRENCY:-3}}"
TIMEOUT_VALUE="${GUNICORN_TIMEOUT:-120}"

exec gunicorn afrilux_sav.wsgi:application \
  --bind "0.0.0.0:${PORT_VALUE}" \
  --workers "${WORKERS_VALUE}" \
  --timeout "${TIMEOUT_VALUE}"
