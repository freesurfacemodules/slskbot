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

URL=${SLSKD_API_URL:-http://localhost:5030}/application/version

echo "Requesting $URL"
wget -S -O - "$URL"
