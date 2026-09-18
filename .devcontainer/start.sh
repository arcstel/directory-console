#!/usr/bin/env bash
# Codespaces bootstrap: build and start the Samba AD DC + console, then wait
# for the console to answer on port 8000 (which Codespaces auto-forwards).
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Building and starting the stack (first run takes a few minutes)…"
docker compose up -d --build

echo "==> Waiting for the console to become healthy…"
for i in $(seq 1 90); do
  if curl -sf http://localhost:8000/api/health >/dev/null 2>&1; then
    echo "==> Directory Control Center is up at http://localhost:8000"
    curl -s http://localhost:8000/api/health || true
    echo
    exit 0
  fi
  sleep 5
done

echo "!! Timed out waiting for the console. Inspect logs with: docker compose logs"
docker compose ps || true
exit 1
