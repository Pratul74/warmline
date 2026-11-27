#!/usr/bin/env bash
# Deploys one image tag: pull, check the nginx config, migrate, restart, health check.
# If the health check fails, the previous tag is started again (automatic rollback).
# Usage: ./deploy.sh <tag>      (the tag is the git commit SHA the images were built from)
#
# Rolling back the app does NOT roll back the database: migrations must stay backward
# compatible (add, never drop or rename in the same release). Certificates are never touched.
set -euo pipefail
cd "$(dirname "$0")"

TAG="${1:-}"
if [[ ! "$TAG" =~ ^[A-Za-z0-9._-]{1,128}$ ]]; then
    echo "usage: $0 <image-tag>" >&2
    exit 2
fi

log() { echo "[deploy $(date -u +%H:%M:%SZ)] $*"; }

# The public URL, read from .env (one place for configuration). The check goes through
# DNS, nginx and TLS, exactly like a real visitor.
BASE_URL="$(sed -n 's/^PUBLIC_CHAT_BASE_URL=//p' .env | tr -d '\r' | tail -n 1)"
HEALTH_URL="${BASE_URL%/}/api/health"
PREVIOUS="$(cat current_tag 2>/dev/null || true)"

health_ok() {
    local attempt
    for attempt in $(seq 1 30); do
        if curl -fsS --max-time 5 ${CURL_CA_FILE:+--cacert "$CURL_CA_FILE"} "$HEALTH_URL" > /dev/null; then
            return 0
        fi
        sleep 2
    done
    return 1
}

# Applies migrations with the new image, unless the database is already NEWER than the
# image (a rollback to an older tag): then the image does not know the database's
# revision, and "alembic upgrade" would fail, so migrations are skipped.
migrate() {
    local tag="$1" db_rev
    APP_TAG="$tag" ./compose.sh up -d --wait db
    db_rev="$(APP_TAG="$tag" ./compose.sh exec -T db sh -c \
        'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT version_num FROM alembic_version" 2>/dev/null' || true)"
    db_rev="$(echo "$db_rev" | tr -d '\r[:space:]')"
    if [ -n "$db_rev" ] && ! APP_TAG="$tag" ./compose.sh run --rm --no-deps -T api alembic show "$db_rev" > /dev/null 2>&1; then
        log "database is at revision $db_rev, which image $tag does not know (the database is newer): skipping migrations"
        return 0
    fi
    log "running migrations (database at ${db_rev:-empty})"
    APP_TAG="$tag" ./compose.sh run --rm -T api alembic upgrade head
}

start() {
    APP_TAG="$1" ./compose.sh up -d --remove-orphans
}

log "deploying $TAG (currently running: ${PREVIOUS:-nothing})"

if [ "${SKIP_PULL:-0}" != "1" ]; then
    APP_TAG="$TAG" ./compose.sh pull api web
fi

log "checking the nginx config of the new web image (nginx -t)"
APP_TAG="$TAG" ./compose.sh run --rm --no-deps -T web nginx -t

migrate "$TAG"
start "$TAG"

if health_ok; then
    echo "$TAG" > current_tag
    if [ -n "$PREVIOUS" ] && [ "$PREVIOUS" != "$TAG" ]; then
        echo "$PREVIOUS" > previous_tag
    fi
    log "OK: $TAG is live and $HEALTH_URL answers 200"
    exit 0
fi

log "FAILED: $HEALTH_URL did not answer 200 within 60 s with $TAG"
APP_TAG="$TAG" ./compose.sh logs --tail 30 api web || true

if [ -n "$PREVIOUS" ] && [ "$PREVIOUS" != "$TAG" ]; then
    log "rolling back to $PREVIOUS"
    start "$PREVIOUS"
    if health_ok; then
        log "rolled back: $PREVIOUS is live and healthy"
    else
        log "the rollback is ALSO unhealthy: manual action needed (see the runbook)"
    fi
else
    log "no previous tag to roll back to"
fi
exit 1
