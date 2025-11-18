#!/bin/sh
set -eu

REQUIRED_VARS="SLSK_USERNAME SLSK_PASSWORD SLSKD_API_KEY SLSKD_ADMIN_USER SLSKD_ADMIN_PASSWORD"
for var in $REQUIRED_VARS; do
  eval "value=\${$var:-}"
  if [ -z "$value" ]; then
    echo "$var must be set to generate slskd.yml" >&2
    exit 1
  fi
done

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
ADMIN_USER_ESC=$(escape_sed "$SLSKD_ADMIN_USER")
ADMIN_PASS_ESC=$(escape_sed "$SLSKD_ADMIN_PASSWORD")

mkdir -p "$(dirname "$OUTPUT")"

tmpfile=$(mktemp)
trap 'rm -f "$tmpfile"' EXIT

sed \
  -e 's|\${SLSK_USERNAME}|'"$USERNAME_ESC"'|g' \
  -e 's|\${SLSK_PASSWORD}|'"$PASSWORD_ESC"'|g' \
  -e 's|\${SLSKD_API_KEY}|'"$APIKEY_ESC"'|g' \
  -e 's|\${SLSKD_ADMIN_USER}|'"$ADMIN_USER_ESC"'|g' \
  -e 's|\${SLSKD_ADMIN_PASSWORD}|'"$ADMIN_PASS_ESC"'|g' \
  "$TEMPLATE" > "$tmpfile"

mv "$tmpfile" "$OUTPUT"
echo "Rendered $OUTPUT from template."
