#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="/opt/bot/jarvis-do-cerrado"
BRANCH="main"
LOG="/var/log/jarvis_deploy.log"

exec >>"$LOG" 2>&1
printf '\n===== DEPLOY %s =====\n' "$(date --iso-8601=seconds)"

cd "$PROJECT_DIR"
git fetch origin "$BRANCH"
git merge --ff-only "origin/$BRANCH"

docker compose config --quiet
docker compose build homebot
docker compose up -d --no-deps --remove-orphans homebot

for attempt in $(seq 1 30); do
    status=$(docker inspect jarvis_cerrado --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}')
    printf 'health attempt %s: %s\n' "$attempt" "$status"
    if [[ "$status" == "healthy" ]]; then
        curl --fail --silent --show-error --max-time 10 http://127.0.0.1:8000/api/system/health
        printf '\nDEPLOY FINALIZADO COM SUCESSO\n'
        exit 0
    fi
    sleep 3
done

printf 'ERRO: jarvis_cerrado nao ficou healthy no prazo\n'
docker logs --tail 100 jarvis_cerrado
exit 1
