#!/usr/bin/env bash
set -euo pipefail

PROD_ENV_FILE="${PROD_ENV_FILE:-.env.prod}"
TARGET="root@159.69.2.19:/root/.env"

if [ ! -f "$PROD_ENV_FILE" ]; then
  echo "Production env file '$PROD_ENV_FILE' not found." >&2
  exit 1
fi

echo "Copying $PROD_ENV_FILE to $TARGET"
scp "$PROD_ENV_FILE" "$TARGET"
echo "Done."
