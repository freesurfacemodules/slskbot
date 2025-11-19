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

REQUIRED_VARS=(HOST_DOWNLOADS_PATH HOST_SHARES_PATH HOST_SLSKD_DATA HOST_NAVIDROME_DATA)
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

CONFIG_FILE="config/nginx.dev.conf"
if [ ! -f "$CONFIG_FILE" ]; then
  echo "Missing $CONFIG_FILE" >&2
  exit 1
fi

docker compose up -d --build "$@"
