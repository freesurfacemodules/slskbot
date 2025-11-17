#!/bin/sh
set -eu

if [ -z "${SLSK_USERNAME:-}" ]; then
  echo "SLSK_USERNAME must be set to generate slskd.yml" >&2
  exit 1
fi

if [ -z "${SLSK_PASSWORD:-}" ]; then
  echo "SLSK_PASSWORD must be set to generate slskd.yml" >&2
  exit 1
fi

if [ -z "${SLSKD_API_KEY:-}" ]; then
  echo "SLSKD_API_KEY must be set to generate slskd.yml" >&2
  exit 1
fi

TEMPLATE=/templates/slskd.yml.template
OUTPUT=/app/slskd.yml

if [ ! -f "$TEMPLATE" ]; then
  echo "Template $TEMPLATE not found" >&2
  exit 1
fi

escape_sed() {
  printf '%s' "$1" | sed -e 's/[\\/&|]/\\&/g'
}

USERNAME_ESC=$(escape_sed "$SLSK_USERNAME")
PASSWORD_ESC=$(escape_sed "$SLSK_PASSWORD")
APIKEY_ESC=$(escape_sed "$SLSKD_API_KEY")

tmpfile=$(mktemp)
trap 'rm -f "$tmpfile"' EXIT

sed \
  -e 's|\${SLSK_USERNAME}|'"'""$USERNAME_ESC""'"'|g' \
  -e 's|\${SLSK_PASSWORD}|'"'""$PASSWORD_ESC""'"'|g' \
  -e 's|\${SLSKD_API_KEY}|'"'""$APIKEY_ESC""'"'|g' \
  "$TEMPLATE" > "$tmpfile"

mv "$tmpfile" "$OUTPUT"
echo "Rendered $OUTPUT from template."
