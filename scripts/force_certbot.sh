#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"
if [ ! -f "$ENV_FILE" ]; then
  echo "Env file '$ENV_FILE' not found" >&2
  exit 1
fi

set -a
. "$ENV_FILE"
set +a

REQUIRED_VARS=(LETSENCRYPT_EMAIL SLSKD_DOMAIN NAVIDROME_DOMAIN)
for var in "${REQUIRED_VARS[@]}"; do
  if [ -z "${!var:-}" ]; then
    echo "Missing required variable $var in $ENV_FILE" >&2
    exit 1
  fi
done

COMPOSE_CMD=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

"${COMPOSE_CMD[@]}" run --rm certbot-init \
  certonly --webroot --webroot-path=/var/www/certbot \
  --email "$LETSENCRYPT_EMAIL" --agree-tos --no-eff-email --force-renewal \
  -d "$SLSKD_DOMAIN" -d "$NAVIDROME_DOMAIN"

"${COMPOSE_CMD[@]}" exec nginx nginx -s reload || true
