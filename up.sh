#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ "$#" -eq 0 ]; then
  set -- up -d
fi

docker compose \
  -f docker-compose.yml \
  -f docker-compose.https.yml \
  -f docker-compose.production.yml \
  -f docker-compose.smtp.yml \
  --env-file .env \
  "$@"
