#!/usr/bin/env bash
set -euo pipefail

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

log() {
  printf '[QQBridge] %s\n' "$*"
}

assert_absolute_path() {
  case "$1" in
    /*) ;;
    *) die "path must be absolute: $1" ;;
  esac
}

target_home() {
  local user="$1"
  getent passwd "$user" | cut -d: -f6
}

as_target() {
  local user="$1"
  shift
  if [[ "$user" == "root" || "$(id -un)" == "$user" ]]; then
    "$@"
  else
    runuser -u "$user" -- "$@"
  fi
}

compose() {
  local user="$1"
  local install_root="$2"
  local env_file="$3"
  shift 3
  local release
  release="$(readlink -f "$install_root/current")"
  as_target "$user" docker compose \
    --project-directory "$release" \
    --env-file "$env_file" \
    -f "$release/compose.yaml" \
    "$@"
}

secure_instance_files() {
  local instance="$1"
  chmod 600 "$instance/.env"
  find "$instance/config" -type f -name '*.toml' -exec chmod 600 {} +
  find "$instance/napcat/config" -type f -name '*.json' -exec chmod 600 {} +
  find "$instance/plugins" "$instance/data" -type f \( \
    -name 'config.toml' -o -iname '*webui*' -o -iname 'credentials.json' \
    -o -iname 'token.json' -o -iname 'tokens.json' -o -iname 'auth.json' \
    \) -exec chmod 600 {} +
}

wait_for_health() {
  local container="$1"
  local timeout="${2:-180}"
  local started
  started="$(date +%s)"
  while (( $(date +%s) - started < timeout )); do
    local status
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container" 2>/dev/null || true)"
    if [[ "$status" == "healthy" || "$status" == "running" ]]; then
      return 0
    fi
    sleep 5
  done
  printf 'Health check timed out for %s (status: %s). Application logs were not printed.\n' \
    "$container" "${status:-unavailable}" >&2
  return 1
}

backup_instance() {
  local install_root="$1"
  local instance="$2"
  local previous_version="$3"
  local backup_id
  backup_id="$(date -u +%Y%m%dT%H%M%S%NZ)"
  local dir="$install_root/backups/$backup_id"
  # A collision must never overwrite an earlier backup.
  mkdir -m 700 "$dir" || return 1
  (umask 077; tar -C "$(dirname "$instance")" \
    --exclude='default/logs/*' \
    -czf "$dir/instance.tar.gz" "$(basename "$instance")") || return 1
  tar -tzf "$dir/instance.tar.gz" >/dev/null || return 1
  printf 'BACKUP_ID=%s\nPREVIOUS_VERSION=%s\nCREATED_UTC=%s\n' \
    "$backup_id" "$previous_version" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$dir/metadata.env" || return 1
  chmod 600 "$dir/instance.tar.gz" "$dir/metadata.env" || return 1
  printf '%s\n' "$backup_id"
}

prune_backups() {
  local install_root="$1"
  local keep="${2:-3}"
  mapfile -t backups < <(find "$install_root/backups" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -r)
  local index=0
  for backup in "${backups[@]}"; do
    index=$((index + 1))
    if (( index > keep )); then
      rm -rf -- "$install_root/backups/$backup"
    fi
  done
}
