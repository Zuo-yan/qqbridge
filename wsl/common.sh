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
  docker logs --tail 80 "$container" >&2 || true
  return 1
}

backup_instance() {
  local install_root="$1"
  local instance="$2"
  local previous_version="$3"
  local backup_id
  backup_id="$(date -u +%Y%m%dT%H%M%SZ)"
  local dir="$install_root/backups/$backup_id"
  mkdir -p "$dir"
  tar -C "$(dirname "$instance")" \
    --exclude='./default/logs/*' \
    -czf "$dir/instance.tar.gz" "$(basename "$instance")"
  printf 'BACKUP_ID=%s\nPREVIOUS_VERSION=%s\nCREATED_UTC=%s\n' \
    "$backup_id" "$previous_version" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$dir/metadata.env"
  chmod 600 "$dir/instance.tar.gz" "$dir/metadata.env"
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
