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

REQUIRED_VARS=(
  HOST_DOWNLOADS_PATH
  HOST_SHARES_PATH
  HOST_SLSKD_DATA
  HOST_NAVIDROME_DATA
  SLSKD_DOMAIN
  NAVIDROME_DOMAIN
  LETSENCRYPT_EMAIL
)

for var in "${REQUIRED_VARS[@]}"; do
  if [ -z "${!var:-}" ]; then
    echo "Required variable $var is missing in $ENV_FILE" >&2
    exit 1
  fi
done

ensure_dir() {
  local path="$1"
  if [ -z "$path" ]; then
    return
  fi
  if [ ! -d "$path" ]; then
    mkdir -p "$path"
  fi
}

maybe_chown() {
  local dir="$1"
  if [ -O "$dir" ]; then
    return
  fi
  chown -R "$(id -u):$(id -g)" "$dir" 2>/dev/null || true
}

fix_permissions() {
  local dir="$1"
  ensure_dir "$dir"
  maybe_chown "$dir"
  chmod -R u+rwX,g+rwX "$dir" || true
}

fix_permissions "$HOST_DOWNLOADS_PATH"
fix_permissions "$HOST_SHARES_PATH"
fix_permissions "$HOST_SLSKD_DATA"
fix_permissions "$HOST_NAVIDROME_DATA"

mkdir -p certbot/www certbot/letsencrypt

# Render nginx prod config
./scripts/render_nginx_conf.sh

LIVE_DIR="certbot/letsencrypt/live/$SLSKD_DOMAIN"
ensure_dir "$LIVE_DIR"

create_dummy_cert() {
  local cert="$LIVE_DIR/fullchain.pem"
  local key="$LIVE_DIR/privkey.pem"
  local chain="$LIVE_DIR/chain.pem"
  local certpem="$LIVE_DIR/cert.pem"

  if [ -f "$cert" ] && [ -f "$key" ]; then
    return
  fi

  echo "Generating temporary self-signed certificate for $SLSKD_DOMAIN"
  openssl req -x509 -nodes -newkey rsa:2048 -days 2 \
    -keyout "$key" -out "$cert" \
    -subj "/CN=$SLSKD_DOMAIN" \
    -addext "subjectAltName=DNS:$SLSKD_DOMAIN,DNS:$NAVIDROME_DOMAIN" >/dev/null 2>&1
  cp "$cert" "$chain"
  cp "$cert" "$certpem"
}

create_dummy_cert

COMPOSE_CMD=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

"${COMPOSE_CMD[@]}" up -d --build "$@"

# Obtain/renew certificates
"${COMPOSE_CMD[@]}" run --rm certbot-init || true

# Reload nginx to pick up any new certificates
"${COMPOSE_CMD[@]}" exec nginx nginx -s reload || true
