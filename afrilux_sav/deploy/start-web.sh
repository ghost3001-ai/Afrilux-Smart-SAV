#!/bin/sh
set -e

PORT_VALUE="${PORT:-8000}"
WORKERS_VALUE="${GUNICORN_WORKERS:-${WEB_CONCURRENCY:-3}}"
TIMEOUT_VALUE="${GUNICORN_TIMEOUT:-120}"
WORKER_CLASS_VALUE="${GUNICORN_WORKER_CLASS:-gthread}"
THREADS_VALUE="${GUNICORN_THREADS:-8}"
KEEPALIVE_VALUE="${GUNICORN_KEEPALIVE:-5}"

exec gunicorn afrilux_sav.wsgi:application \
  --bind "0.0.0.0:${PORT_VALUE}" \
  --worker-class "${WORKER_CLASS_VALUE}" \
  --workers "${WORKERS_VALUE}" \
  --threads "${THREADS_VALUE}" \
  --timeout "${TIMEOUT_VALUE}" \
  --keep-alive "${KEEPALIVE_VALUE}"
