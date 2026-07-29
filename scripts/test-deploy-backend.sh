#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly DEPLOY_SCRIPT="${SCRIPT_DIR}/deploy-backend.sh"
readonly TEST_ROOT="$(mktemp -d)"
readonly REMOTE="${TEST_ROOT}/origin.git"
readonly AUTHOR_REPO="${TEST_ROOT}/author"
readonly DEPLOY_REPO="${TEST_ROOT}/deploy"
readonly MOCK_BIN="${TEST_ROOT}/bin"

cleanup() {
  rm -rf -- "$TEST_ROOT"
}
trap cleanup EXIT

fail() {
  printf 'deployment test failed: %s\n' "$*" >&2
  exit 1
}

commit_and_push() {
  local message="$1"

  git -C "$AUTHOR_REPO" add .
  git -C "$AUTHOR_REPO" commit -q -m "$message"
  git -C "$AUTHOR_REPO" push -q origin main
  git -C "$AUTHOR_REPO" rev-parse HEAD
}

image_for() {
  local digit="$1"

  printf 'ghcr.io/example/event-manager-backend@sha256:%064d' "$digit"
}

mkdir -p "$MOCK_BIN"

cat > "${MOCK_BIN}/docker" <<'MOCK_DOCKER'
#!/usr/bin/env bash
set -u

if [[ "${1:-}" == "inspect" ]]; then
  if [[ "${*: -1}" == "scheduler-id" ]]; then
    printf 'true\n'
  else
    printf 'healthy\n'
  fi
  exit 0
fi

if [[ "${1:-}" == "pull" ]]; then
  exit 0
fi

[[ "${1:-}" == "compose" ]] || exit 1
shift
while [[ "${1:-}" == "--env-file" || "${1:-}" == "-f" ]]; do
  shift 2
done

arguments=" $* "
case "$arguments" in
  *" ps -q mysql "*) printf 'mysql-id\n' ;;
  *" ps -q api "*) printf 'api-id\n' ;;
  *" ps -q scheduler "*) printf 'scheduler-id\n' ;;
  *" exec -T mysql "*)
    cat >/dev/null
    printf '%s\n' '-- mock dump' '-- Dump completed on 2026-01-01'
    ;;
  *" exec -T api alembic current "*)
    cat >/dev/null
    printf '0001 (head)\n'
    ;;
  *" exec -T api alembic heads "*)
    cat >/dev/null
    printf '0001 (head)\n'
    ;;
  *" run --rm migrate "*)
    cat >/dev/null
    [[ "${MOCK_MIGRATION_FAIL:-0}" != "1" ]]
    ;;
  *) exit 0 ;;
esac
MOCK_DOCKER

cat > "${MOCK_BIN}/curl" <<'MOCK_CURL'
#!/usr/bin/env bash
set -u

if [[ -n "${MOCK_FAIL_IMAGE:-}" && "${BACKEND_IMAGE:-}" == "$MOCK_FAIL_IMAGE" ]]; then
  exit 22
fi
printf '{"status":"ok"}'
MOCK_CURL

chmod +x "${MOCK_BIN}/docker" "${MOCK_BIN}/curl"

git init -q --bare -b main "$REMOTE"
git init -q -b main "$AUTHOR_REPO"
git -C "$AUTHOR_REPO" config user.name "Deployment Test"
git -C "$AUTHOR_REPO" config user.email "deployment-test@example.com"
git -C "$AUTHOR_REPO" remote add origin "$REMOTE"
mkdir -p "${AUTHOR_REPO}/backend/alembic/versions"
touch "${AUTHOR_REPO}/backend/alembic/versions/.keep"
printf 'services: {}\n' > "${AUTHOR_REPO}/docker-compose.backend.yml"
printf '.env.backend\n.deployment/\n' > "${AUTHOR_REPO}/.gitignore"
printf 'CADDY_ADDRESS=api.example.com\n' > "${AUTHOR_REPO}/.env.backend"
printf 'first\n' > "${AUTHOR_REPO}/application.txt"
first_sha="$(commit_and_push "first")"

git clone -q "$REMOTE" "$DEPLOY_REPO"
printf 'CADDY_ADDRESS=api.example.com\n' > "${DEPLOY_REPO}/.env.backend"

first_image="$(image_for 1)"
(
  cd "$DEPLOY_REPO"
  PATH="${MOCK_BIN}:$PATH" bash -s -- "$first_sha" "$first_image" < "$DEPLOY_SCRIPT"
)
[[ "$(sed -n '1p' "${DEPLOY_REPO}/.deployment/last-successful")" == "$first_sha" ]] \
  || fail "first deployment state was not recorded"
[[ "$(find "${DEPLOY_REPO}/.deployment/backups" -type f -name '*.sql' | wc -l)" -eq 1 ]] \
  || fail "first deployment did not create exactly one backup"

printf 'second\n' > "${AUTHOR_REPO}/application.txt"
second_sha="$(commit_and_push "second")"
second_image="$(image_for 2)"
(
  cd "$DEPLOY_REPO"
  PATH="${MOCK_BIN}:$PATH" "$DEPLOY_SCRIPT" "$second_sha" "$second_image"
)
[[ "$(sed -n '1p' "${DEPLOY_REPO}/.deployment/last-successful")" == "$second_sha" ]] \
  || fail "second deployment state was not recorded"
[[ "$(find "${DEPLOY_REPO}/.deployment/backups" -type f -name '*.sql' | wc -l)" -eq 1 ]] \
  || fail "no-migration deployment created an unnecessary backup"

printf 'third\n' > "${AUTHOR_REPO}/application.txt"
third_sha="$(commit_and_push "third")"
third_image="$(image_for 3)"
if (
  cd "$DEPLOY_REPO"
  PATH="${MOCK_BIN}:$PATH" MOCK_FAIL_IMAGE="$third_image" \
    "$DEPLOY_SCRIPT" "$third_sha" "$third_image"
); then
  fail "unhealthy deployment unexpectedly succeeded"
fi
[[ "$(sed -n '1p' "${DEPLOY_REPO}/.deployment/last-successful")" == "$second_sha" ]] \
  || fail "failed deployment changed successful state"
[[ "$(git -C "$DEPLOY_REPO" rev-parse HEAD)" == "$second_sha" ]] \
  || fail "no-migration failure did not roll back the checkout"

printf '# migration\n' > "${AUTHOR_REPO}/backend/alembic/versions/0002_test.py"
fourth_sha="$(commit_and_push "migration")"
fourth_image="$(image_for 4)"
if (
  cd "$DEPLOY_REPO"
  PATH="${MOCK_BIN}:$PATH" MOCK_MIGRATION_FAIL=1 \
    "$DEPLOY_SCRIPT" "$fourth_sha" "$fourth_image"
); then
  fail "failed migration unexpectedly succeeded"
fi
[[ "$(sed -n '1p' "${DEPLOY_REPO}/.deployment/last-successful")" == "$second_sha" ]] \
  || fail "failed migration changed successful state"
[[ "$(git -C "$DEPLOY_REPO" rev-parse HEAD)" == "$fourth_sha" ]] \
  || fail "migration failure incorrectly rolled back the checkout"
[[ "$(find "${DEPLOY_REPO}/.deployment/backups" -type f -name '*.sql' | wc -l)" -eq 2 ]] \
  || fail "migration failure did not preserve its verified backup"

printf 'deployment script tests passed\n'
