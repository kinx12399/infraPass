#!/usr/bin/env bash
set -euo pipefail
# Run as the checkout owner, not root. Requires scoped sudo for deployment.
# Usage: bash deploy/update.sh web|was
role="${1:-}"
case "$role" in web|was) ;; *) echo 'Usage: bash deploy/update.sh web|was'; exit 2;; esac
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
if [[ -n "$(git status --porcelain)" ]]; then
  echo 'Checkout has local changes. Resolve before deployment.' >&2; exit 1
fi
git pull --ff-only
if [[ "$role" == web ]]; then
  sudo install -d /var/www/infrapass
  sudo install -m 0644 web/index.html web/app.js web/styles.css /var/www/infrapass/
  sudo nginx -t
  sudo systemctl reload nginx
  curl --fail --silent http://127.0.0.1/healthz
else
  .venv/bin/python -m pip install -r requirements.txt
  # Schema changes are a separate, reviewed step on one WAS only.
  sudo install -m 0644 deploy/infrapass.service /etc/systemd/system/infrapass.service
  sudo systemctl daemon-reload
  sudo systemctl restart infrapass
  healthy=false
  for attempt in {1..15}; do
    if curl --fail --silent http://127.0.0.1:8080/api/health/ready; then healthy=true; break; fi
    sleep 2
  done
  if [[ "$healthy" != true ]]; then echo 'WAS health check failed; keep node out of LB.' >&2; exit 1; fi
fi
git rev-parse --short HEAD
