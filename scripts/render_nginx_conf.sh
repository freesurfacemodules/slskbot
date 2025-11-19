#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"
TEMPLATE="config/nginx.prod.conf.template"
OUTPUT="config/nginx.prod.conf"

if [ ! -f "$ENV_FILE" ]; then
  echo "Env file '$ENV_FILE' not found" >&2
  exit 1
fi

set -a
. "$ENV_FILE"
set +a

for var in SLSKD_DOMAIN NAVIDROME_DOMAIN; do
  if [ -z "${!var:-}" ]; then
    echo "Missing required variable $var" >&2
    exit 1
  fi
done

mkdir -p config

tmpfile=$(mktemp)
trap 'rm -f "$tmpfile"' EXIT

sed \
  -e "s|\${SLSKD_DOMAIN}|$SLSKD_DOMAIN|g" \
  -e "s|\${NAVIDROME_DOMAIN}|$NAVIDROME_DOMAIN|g" \
  "$TEMPLATE" > "$tmpfile"

mv "$tmpfile" "$OUTPUT"
echo "Rendered $OUTPUT"
