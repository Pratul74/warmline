#!/usr/bin/env bash
# Certbot runs this as root after every successful issue or renewal. Install it as
# /etc/letsencrypt/renewal-hooks/deploy/warmline.sh (root-owned, mode 755).
#
# nginx runs as uid 101 and cannot read /etc/letsencrypt (root only). So this copies the
# certificate and key to /opt/warmline/certs, readable by uid 101 only, checks the nginx
# config and RELOADS nginx (no restart, no dropped connections). The keys never leave the
# server and are never in the repo or an image.
set -euo pipefail

APP_DIR=/opt/warmline
NGINX_UID=101
SOURCE="${RENEWED_LINEAGE:?this script is run by certbot, which sets RENEWED_LINEAGE}"
DEST="$APP_DIR/certs"

install -d -m 700 -o "$NGINX_UID" -g "$NGINX_UID" "$DEST"
install -m 644 -o "$NGINX_UID" -g "$NGINX_UID" "$SOURCE/fullchain.pem" "$DEST/fullchain.pem.new"
install -m 600 -o "$NGINX_UID" -g "$NGINX_UID" "$SOURCE/privkey.pem" "$DEST/privkey.pem.new"
mv -f "$DEST/fullchain.pem.new" "$DEST/fullchain.pem"
mv -f "$DEST/privkey.pem.new" "$DEST/privkey.pem"
echo "certificate copied to $DEST"

if ! "$APP_DIR/compose.sh" ps --status running --services | grep -qx web; then
    echo "nginx (web) is not running: it will load the certificate when it starts"
    exit 0
fi

# First certificate: nginx is still on the HTTP-only bootstrap config, which a reload
# cannot change. Recreate the container once so it picks the HTTPS config.
if "$APP_DIR/compose.sh" exec -T web grep -q WARMLINE_BOOTSTRAP /etc/nginx/conf.d/default.conf; then
    echo "nginx is on the bootstrap config: recreating it once to switch to HTTPS"
    "$APP_DIR/compose.sh" up -d --no-deps --force-recreate web
    exit 0
fi

"$APP_DIR/compose.sh" exec -T web nginx -t
"$APP_DIR/compose.sh" exec -T web nginx -s reload
echo "nginx reloaded with the new certificate"
