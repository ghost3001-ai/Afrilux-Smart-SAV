#!/bin/sh
set -e

if [ -n "${SCHEDULER_ORGANIZATION_SLUG:-}" ]; then
  exec python manage.py run_platform_scheduler \
    --interval-seconds "${SCHEDULER_INTERVAL_SECONDS:-60}" \
    --organization-slug "${SCHEDULER_ORGANIZATION_SLUG}"
fi

exec python manage.py run_platform_scheduler \
  --interval-seconds "${SCHEDULER_INTERVAL_SECONDS:-60}"
