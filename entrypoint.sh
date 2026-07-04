#!/usr/bin/env bash
set -e

# Ensure the entrypoint script is executable (this is unnecessary here, should be fixed in the Dockerfile or locally)
# Removed chmod +x /entrypoint.sh from inside the script as it needs to be done outside before Docker runs it.

# Simple entrypoint to optionally run migrations and then start
# either the web server (Gunicorn) or the Celery worker.
#
# Behaviour is controlled by:
# - RUN_MIGRATIONS_ON_START=true|false (default: true for web role)
# - SERVICE_ROLE=web|worker (or first CLI arg)

ROLE="${SERVICE_ROLE:-$1}"

if [ -z "${ROLE}" ]; then
  ROLE="web"
fi

echo "Container starting with role: ${ROLE}"

run_migrations_if_needed() {
  # By default run migrations for web; workers usually don't need it
  local default_run="false"
  if [ "${ROLE}" = "web" ]; then
    default_run="true"
  fi

  local flag="${RUN_MIGRATIONS_ON_START:-$default_run}"

  if [ "${flag}" = "true" ]; then
    echo "Running database migrations..."
    python manage.py migrate --noinput || echo "Migrations failed (or DB unavailable); continuing..."
  else
    echo "Skipping database migrations (RUN_MIGRATIONS_ON_START=${flag})"
  fi
}

case "${ROLE}" in
  web)
    run_migrations_if_needed
    echo "Starting Gunicorn web server..."
    exec gunicorn -c gunicorn_config.py esign.wsgi:application
    ;;
  worker)
    run_migrations_if_needed
    CELERY_CONCURRENCY="${CELERY_WORKER_CONCURRENCY:-4}"
    echo "Starting Celery worker (concurrency=${CELERY_CONCURRENCY})..."
    exec celery -A esign worker -l info --concurrency="${CELERY_CONCURRENCY}" -Q notifications,signing
    ;;
  *)
    # If an explicit command is provided, just exec it
    echo "Unknown role '${ROLE}', executing arguments as command: $*"
    exec "$@"
    ;;
esac
