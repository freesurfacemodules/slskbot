#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"
COMPOSE_CMD=(docker compose)

if [ ! -f "$ENV_FILE" ]; then
  echo "Env file '$ENV_FILE' not found. Set ENV_FILE or create .env." >&2
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
    mkdir -p "$path" 2>/dev/null || {
      if command -v sudo >/dev/null 2>&1; then
        sudo mkdir -p "$path"
      else
        echo "Failed to create $path. Create it manually." >&2
        exit 1
      fi
    }
  fi
}

maybe_sudo() {
  if [ "$EUID" -eq 0 ]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    "$@"
  fi
}

fix_permissions() {
  local dir="$1"
  ensure_dir "$dir"
  if [ ! -O "$dir" ]; then
    maybe_sudo chown -R "$(id -u):$(id -g)" "$dir"
  fi
  maybe_sudo chmod -R u+rwX,g+rwX "$dir"
}

fix_permissions "$HOST_DOWNLOADS_PATH"
fix_permissions "$HOST_SHARES_PATH"
fix_permissions "$HOST_SLSKD_DATA"
fix_permissions "$HOST_NAVIDROME_DATA"

echo "Directories prepared. Launching docker compose..."
"${COMPOSE_CMD[@]}" up -d --build "$@"
