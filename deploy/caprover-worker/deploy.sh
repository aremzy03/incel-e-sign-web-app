#!/usr/bin/env bash
# Deploy the esign Celery worker to CapRover using the pre-built GHCR image.
#
# Prerequisites:
#   npm install -g caprover
#   caprover login   # once per machine
#
# Usage (from repo root):
#   ./deploy/caprover-worker/deploy.sh
#
# Override the CapRover app name:
#   CAPROVER_APP_NAME=esign-worker ./deploy/caprover-worker/deploy.sh
#
# Configure the same env vars as the web app in the CapRover dashboard
# (DATABASE_URL, CELERY_BROKER_URL, SECRET_KEY, etc.). Migrations are skipped
# on worker start (RUN_MIGRATIONS_ON_START=false).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="${CAPROVER_APP_NAME:-esign-celery-worker}"

if ! command -v caprover >/dev/null 2>&1; then
  echo "Error: caprover CLI not found. Install with: npm install -g caprover" >&2
  exit 1
fi

echo "Deploying Celery worker to CapRover app: ${APP_NAME}"
cd "${SCRIPT_DIR}"
caprover deploy -a "${APP_NAME}"
