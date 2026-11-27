#!/bin/sh
# Runs at container start (the nginx image runs every script in /docker-entrypoint.d/).
# Picks the site config: HTTPS when a readable certificate is mounted, otherwise the
# HTTP-only bootstrap config that lets Certbot obtain the first certificate.
set -eu

CERTS=/etc/nginx/certs
if [ -r "$CERTS/fullchain.pem" ] && [ -r "$CERTS/privkey.pem" ]; then
    cp /etc/nginx/warmline/site-https.conf /etc/nginx/conf.d/default.conf
    echo "$0: certificate found, using the HTTPS site config"
else
    cp /etc/nginx/warmline/site-http-only.conf /etc/nginx/conf.d/default.conf
    echo "$0: no readable certificate in $CERTS, using the HTTP-only bootstrap config"
fi
