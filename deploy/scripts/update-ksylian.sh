#!/usr/bin/env bash
set -euo pipefail

TARGET_VERSION="${1:-${KSYLIAN_TARGET_VERSION:-}}"
APP_DIR="${KSYLIAN_APP_DIR:-/opt/ksylian}"
ENV_FILE="${KSYLIAN_ENV_FILE:-$APP_DIR/deploy/.env}"
COMPOSE_FILE="${KSYLIAN_COMPOSE_FILE:-$APP_DIR/deploy/docker-compose.yml}"
LOG_FILE="${KSYLIAN_UPDATE_LOG:-/var/lib/ksylian-agent/update.log}"

log() {
  mkdir -p "$(dirname "$LOG_FILE")"
  printf "[%s] %s\n" "$(date '+%F %T')" "$*" | tee -a "$LOG_FILE"
}

set_env_var() {
  local key="$1"
  local value="$2"
  local escaped
  escaped="$(printf '%s' "$value" | sed 's/[\/&]/\\&/g')"

  if grep -q "^${key}=" "$ENV_FILE"; then
    sed -i "s/^${key}=.*/${key}=${escaped}/" "$ENV_FILE"
  else
    printf "%s=%s\n" "$key" "$value" >> "$ENV_FILE"
  fi
}

if [[ ! -d "$APP_DIR/.git" ]]; then
  echo "Ksylian app directory is not a git repository: $APP_DIR" >&2
  exit 1
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Docker compose file was not found: $COMPOSE_FILE" >&2
  exit 1
fi

cd "$APP_DIR"
git config --global --add safe.directory "$APP_DIR" >/dev/null 2>&1 || true
log "Fetching release tags"
git fetch --tags --force --prune origin

if [[ -z "$TARGET_VERSION" ]]; then
  TARGET_VERSION="$(git tag --sort=-v:refname | head -n 1)"
fi

if [[ -z "$TARGET_VERSION" ]]; then
  echo "No target version was provided and no git tags were found" >&2
  exit 1
fi

if [[ "$TARGET_VERSION" != v* ]]; then
  echo "Target version must be a release tag like v0.6.6" >&2
  exit 1
fi

log "Starting update to ${TARGET_VERSION}"
git checkout --force "$TARGET_VERSION"
SHA="$(git rev-parse --short HEAD)"

test -f "$ENV_FILE" || cp deploy/.env.example "$ENV_FILE"
set_env_var "KSYLIAN_BUILD_VERSION" "$TARGET_VERSION"
set_env_var "KSYLIAN_BUILD_SHA" "$SHA"

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --build
docker image prune -f >/dev/null || true

if [[ "${EUID:-$(id -u)}" -eq 0 && -x "$APP_DIR/agent/install-agent.sh" ]]; then
  log "Updating host agent"
  (
    cd "$APP_DIR/agent"
    APP_DIR="${KSYLIAN_AGENT_APP_DIR:-/opt/ksylian-agent}" ./install-agent.sh
  )
fi

log "Update to ${TARGET_VERSION} completed (${SHA})"
