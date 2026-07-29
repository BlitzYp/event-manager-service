#!/usr/bin/env bash
set -Eeuo pipefail

readonly TARGET_SHA="${1:-}"
readonly TARGET_IMAGE="${2:-}"
readonly COMPOSE_FILE="docker-compose.backend.yml"
readonly ENV_FILE=".env.backend"
readonly STATE_DIR=".deployment"
readonly STATE_FILE="${STATE_DIR}/last-successful"
readonly BACKUP_DIR="${STATE_DIR}/backups"
readonly BACKUP_RETENTION=5

PREVIOUS_SHA=""
PREVIOUS_IMAGE=""
MIGRATIONS_CHANGED=true
DEPLOYMENT_STARTED=false
CURRENT_BACKUP=""

log() {
  printf '[deploy] %s\n' "$*"
}

fail() {
  log "ERROR: $*" >&2
  exit 1
}

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

read_previous_state() {
  local -a state=()

  [[ -f "$STATE_FILE" ]] || return 0
  mapfile -t state < "$STATE_FILE"
  if [[ "${#state[@]}" -ne 2 ]]; then
    fail "Deployment state is malformed: $STATE_FILE"
  fi
  if [[ ! "${state[0]}" =~ ^[0-9a-f]{40}$ ]]; then
    fail "Previous deployment SHA is invalid"
  fi
  if [[ ! "${state[1]}" =~ ^ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}$ ]]; then
    fail "Previous deployment image is invalid"
  fi

  PREVIOUS_SHA="${state[0]}"
  PREVIOUS_IMAGE="${state[1]}"
}

wait_for_mysql() {
  local container_id=""

  container_id="$(compose ps -q mysql)"
  [[ -n "$container_id" ]] || fail "MySQL container was not created"

  for _ in {1..36}; do
    if [[ "$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' \
      "$container_id")" == "healthy" ]]; then
      return 0
    fi
    sleep 5
  done

  fail "MySQL did not become healthy"
}

wait_for_api() {
  local container_id=""

  container_id="$(compose ps -q api)"
  [[ -n "$container_id" ]] || fail "API container was not created"

  for _ in {1..36}; do
    if [[ "$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' \
      "$container_id")" == "healthy" ]]; then
      return 0
    fi
    sleep 5
  done

  fail "API did not become healthy"
}

verify_scheduler() {
  local container_id=""

  container_id="$(compose ps -q scheduler)"
  [[ -n "$container_id" ]] || fail "Scheduler container was not created"
  [[ "$(docker inspect --format '{{.State.Running}}' "$container_id")" == "true" ]] \
    || fail "Scheduler is not running"
}

verify_migration_state() {
  local current=""
  local heads=""

  current="$(compose exec -T api alembic current </dev/null \
    | sed -E 's/[[:space:]]+\(head\)$//' \
    | sed '/^[[:space:]]*$/d')"
  heads="$(compose exec -T api alembic heads </dev/null \
    | sed -E 's/[[:space:]]+\(head\)$//' \
    | sed '/^[[:space:]]*$/d')"

  [[ -n "$current" && "$current" == "$heads" ]] \
    || fail "Alembic current revision does not match all heads"
}

verify_public_health() {
  local api_host=""

  api_host="$(sed -n 's/^CADDY_ADDRESS=//p' "$ENV_FILE" | tail -n 1 | tr -d '\r')"
  [[ "$api_host" =~ ^[A-Za-z0-9.-]+(:[0-9]+)?$ ]] \
    || fail "CADDY_ADDRESS must contain a production hostname"

  curl \
    --fail-with-body \
    --silent \
    --show-error \
    --retry 10 \
    --retry-delay 3 \
    --retry-all-errors \
    "https://${api_host}/health"
  printf '\n'
}

create_migration_backup() {
  local timestamp=""
  local temporary_backup=""

  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  CURRENT_BACKUP="${BACKUP_DIR}/event-manager-${timestamp}-${TARGET_SHA:0:12}.sql"
  temporary_backup="${CURRENT_BACKUP}.tmp"

  log "Creating pre-migration database backup"
  compose exec -T mysql sh -lc \
    'exec mysqldump --single-transaction --quick --routines --triggers --add-drop-table -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' \
    </dev/null \
    > "$temporary_backup"
  chmod 600 "$temporary_backup"
  [[ -s "$temporary_backup" ]] || fail "Database backup is empty"
  tail -n 5 "$temporary_backup" | grep -q 'Dump completed' \
    || fail "Database backup did not complete successfully"
  mv "$temporary_backup" "$CURRENT_BACKUP"
  log "Backup verified: $CURRENT_BACKUP"
}

rotate_backups() {
  local -a backups=()

  [[ -n "$CURRENT_BACKUP" ]] || return 0
  mapfile -t backups < <(
    find "$BACKUP_DIR" -maxdepth 1 -type f -name 'event-manager-*.sql' -printf '%T@ %p\n' \
      | sort -rn \
      | cut -d' ' -f2-
  )
  for ((index = BACKUP_RETENTION; index < ${#backups[@]}; index++)); do
    rm -- "${backups[$index]}"
  done
}

start_application() {
  compose up -d --no-build --no-deps --force-recreate api scheduler
  wait_for_api
  verify_scheduler
  compose up -d --no-build --no-deps caddy
  verify_migration_state
  verify_public_health
}

rollback_application() {
  log "Attempting safe rollback to $PREVIOUS_SHA"
  export BACKEND_IMAGE="$PREVIOUS_IMAGE"
  git checkout --detach "$PREVIOUS_SHA"
  compose config --quiet
  docker pull "$PREVIOUS_IMAGE"
  start_application
  log "Previous deployment restored successfully"
}

handle_failure() {
  local status="$1"
  trap - ERR
  set +e

  log "Deployment failed; collecting recent service logs"
  compose ps -a
  compose logs --tail=200 migrate api scheduler

  if [[ "$DEPLOYMENT_STARTED" == "true" && "$MIGRATIONS_CHANGED" == "false" \
    && -n "$PREVIOUS_SHA" && -n "$PREVIOUS_IMAGE" ]]; then
    (set -Ee; rollback_application)
    if [[ "$?" -ne 0 ]]; then
      log "Automatic rollback also failed; manual recovery is required" >&2
    fi
  elif [[ "$DEPLOYMENT_STARTED" == "true" && "$MIGRATIONS_CHANGED" == "true" ]]; then
    log "A migration changed; automatic application rollback is disabled" >&2
    log "Use the production runbook for manual recovery; do not downgrade Alembic automatically" >&2
  fi

  exit "$status"
}

trap 'handle_failure $?' ERR

[[ "$TARGET_SHA" =~ ^[0-9a-f]{40}$ ]] || fail "Target SHA must be a full commit SHA"
[[ "$TARGET_IMAGE" =~ ^ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}$ ]] \
  || fail "Target image must be an immutable GHCR digest"
[[ -d .git ]] || fail "Deploy path is not a Git checkout"
[[ -f "$ENV_FILE" ]] || fail "Missing VM-owned $ENV_FILE"
[[ -z "$(git status --porcelain --untracked-files=no)" ]] \
  || fail "Tracked files on the VM contain local changes"

umask 077
mkdir -p "$STATE_DIR" "$BACKUP_DIR"
chmod 700 "$STATE_DIR" "$BACKUP_DIR"
read_previous_state

log "Fetching target revision"
git fetch --prune origin main
git cat-file -e "${TARGET_SHA}^{commit}"
git merge-base --is-ancestor "$TARGET_SHA" origin/main \
  || fail "Target SHA is not part of origin/main"

if [[ -n "$PREVIOUS_SHA" ]]; then
  git cat-file -e "${PREVIOUS_SHA}^{commit}" \
    || fail "Previous deployment commit is unavailable locally"
  if git diff --quiet "$PREVIOUS_SHA" "$TARGET_SHA" -- backend/alembic/versions; then
    MIGRATIONS_CHANGED=false
  fi
fi

log "Checking out exact target revision $TARGET_SHA"
git checkout --detach "$TARGET_SHA"
[[ -f "$COMPOSE_FILE" ]] || fail "Target revision does not contain $COMPOSE_FILE"

export BACKEND_IMAGE="$TARGET_IMAGE"
compose config --quiet
docker pull "$TARGET_IMAGE"

compose up -d mysql
wait_for_mysql

if [[ "$MIGRATIONS_CHANGED" == "true" ]]; then
  create_migration_backup
else
  log "No Alembic version changes detected; skipping deployment-time backup"
fi

DEPLOYMENT_STARTED=true
compose stop api scheduler
compose run --rm migrate </dev/null
start_application

rotate_backups
temporary_state="${STATE_FILE}.tmp"
printf '%s\n%s\n' "$TARGET_SHA" "$TARGET_IMAGE" > "$temporary_state"
mv "$temporary_state" "$STATE_FILE"

log "Deployment completed successfully: $TARGET_SHA"
