#!/usr/bin/env bash
# Puts the previously deployed tag back. Same as ./deploy.sh <previous tag>.
# The database is NOT rolled back (see deploy.sh). Running it twice switches back again.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -s previous_tag ]; then
    echo "No previous tag recorded. Use ./deploy.sh <tag> with a tag you know." >&2
    exit 1
fi
exec ./deploy.sh "$(cat previous_tag)"
