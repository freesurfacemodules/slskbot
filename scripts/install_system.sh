#!/usr/bin/env bash
set -euo pipefail

if [ "$EUID" -ne 0 ]; then
  echo "Please run this script as root (use sudo)."
  exit 1
fi

ENV_FILE="${ENV_FILE:-.env}"
if [ ! -f "$ENV_FILE" ]; then
  echo "Env file '$ENV_FILE' not found." >&2
  exit 1
fi

set -a
. "$ENV_FILE"
set +a

REQUIRED_VARS=(
  HOST_MEDIA_PATH
  HOST_SLSKD_DATA
  HOST_NAVIDROME_DATA
  STORAGEBOX_HOST
  STORAGEBOX_PORT
  STORAGEBOX_USER
  STORAGEBOX_PASSWORD
  STORAGEBOX_REMOTE_PATH
)
for var in "${REQUIRED_VARS[@]}"; do
  if [ -z "${!var:-}" ]; then
    echo "Missing required variable $var in $ENV_FILE" >&2
    exit 1
  fi
done

apt-get update
apt-get install -y docker.io docker-compose-v2 git sshfs sshpass openssl
systemctl enable --now docker

if ! grep -q '^user_allow_other' /etc/fuse.conf; then
  echo 'user_allow_other' >> /etc/fuse.conf
fi

SSH_DIR=/root/.ssh
SSH_KEY="$SSH_DIR/storagebox"
mkdir -p "$SSH_DIR"
chmod 700 "$SSH_DIR"

if [ ! -f "$SSH_KEY" ]; then
  ssh-keygen -t ed25519 -f "$SSH_KEY" -N '' -C "storagebox"
fi

ssh-keyscan -p "$STORAGEBOX_PORT" "$STORAGEBOX_HOST" >> "$SSH_DIR/known_hosts"
sshpass -p "$STORAGEBOX_PASSWORD" ssh-copy-id -i "$SSH_KEY.pub" -p "$STORAGEBOX_PORT" "$STORAGEBOX_USER@$STORAGEBOX_HOST"

ssh -i "$SSH_KEY" -p "$STORAGEBOX_PORT" "$STORAGEBOX_USER@$STORAGEBOX_HOST" \
  "mkdir -p '$STORAGEBOX_REMOTE_PATH'"

LOCAL_MEDIA="$HOST_MEDIA_PATH"
mkdir -p "$LOCAL_MEDIA"
LOCAL_UID=${SUDO_UID:-0}
LOCAL_GID=${SUDO_GID:-0}
chown -R "$LOCAL_UID":"$LOCAL_GID" "$LOCAL_MEDIA"
mkdir -p "$HOST_SLSKD_DATA" "$HOST_NAVIDROME_DATA"
chown -R "$LOCAL_UID":"$LOCAL_GID" "$HOST_SLSKD_DATA" "$HOST_NAVIDROME_DATA"

MOUNT_UNIT=/etc/systemd/system/storagebox-slskd.mount
AUTOMOUNT_UNIT=/etc/systemd/system/storagebox-slskd.automount

cat > "$MOUNT_UNIT" <<MOUNT
[Unit]
Description=SSHFS mount for Hetzner Storage Box (slskd)
After=network-online.target
Wants=network-online.target

[Mount]
What=${STORAGEBOX_USER}@${STORAGEBOX_HOST}:${STORAGEBOX_REMOTE_PATH}
Where=${LOCAL_MEDIA}
Type=fuse.sshfs
Options=_netdev,reconnect,ServerAliveInterval=15,ServerAliveCountMax=3,port=${STORAGEBOX_PORT},IdentityFile=${SSH_KEY},allow_other,default_permissions

[Install]
WantedBy=multi-user.target
MOUNT

cat > "$AUTOMOUNT_UNIT" <<AUTOMOUNT
[Unit]
Description=Automount for Hetzner Storage Box (slskd)

[Automount]
Where=${LOCAL_MEDIA}
TimeoutIdleSec=60

[Install]
WantedBy=multi-user.target
AUTOMOUNT

systemctl daemon-reload
systemctl enable --now storagebox-slskd.automount
systemctl restart storagebox-slskd.mount || true

echo "System dependencies installed and SSHFS mount configured."
