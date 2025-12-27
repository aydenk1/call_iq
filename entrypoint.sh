#!/usr/bin/env bash
set -euo pipefail

mkdir -p /root/.ssh
chmod 700 /root/.ssh

if [ -f /run/secrets/ssh_private_key ]; then
  cp /run/secrets/ssh_private_key /root/.ssh/id_ed25519
  chmod 600 /root/.ssh/id_ed25519
fi

if [ -f /run/secrets/ssh_public_key ]; then
  cp /run/secrets/ssh_public_key /root/.ssh/id_ed25519.pub
  chmod 644 /root/.ssh/id_ed25519.pub
fi

if [ -f /run/secrets/ssh_known_hosts ]; then
  cp /run/secrets/ssh_known_hosts /root/.ssh/known_hosts
  chmod 644 /root/.ssh/known_hosts
fi

if [ -d /opt/web/node_modules ]; then
  mkdir -p /app/web/node_modules
  if [ -z "$(ls -A /app/web/node_modules 2>/dev/null)" ]; then
    cp -a /opt/web/node_modules/. /app/web/node_modules/
  fi
fi

exec "$@"
