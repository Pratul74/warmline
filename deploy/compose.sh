#!/usr/bin/env bash
# Runs "docker compose" for the production stack with the currently deployed image tag.
# Use it for everything by hand too:  ./compose.sh ps   ./compose.sh logs -f web
# The tag comes from APP_TAG if set, otherwise from the file current_tag (written by deploy.sh).
set -euo pipefail
cd "$(dirname "$0")"

if [ -z "${APP_TAG:-}" ]; then
    if [ ! -s current_tag ]; then
        echo "No deployed tag yet: run ./deploy.sh <tag> first, or set APP_TAG." >&2
        exit 1
    fi
    APP_TAG="$(cat current_tag)"
fi
export APP_TAG

exec docker compose -f docker-compose.prod.yml "$@"
