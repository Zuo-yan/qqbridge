#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

PACKAGE=""
INSTALL_ROOT=""
TARGET_USER=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --package) PACKAGE="$2"; shift 2 ;;
    --install-root) INSTALL_ROOT="$2"; shift 2 ;;
    --target-user) TARGET_USER="$2"; shift 2 ;;
    *) die "unknown argument: $1" ;;
  esac
done

[[ -n "$PACKAGE" && -n "$INSTALL_ROOT" && -n "$TARGET_USER" ]] || die "package, install root and target user are required"
INSTANCE="$INSTALL_ROOT/instances/default"
[[ -f "$INSTANCE/.env" ]] || die "instance not found: $INSTANCE"
[[ -e "$INSTALL_ROOT/current" ]] || die "current release is missing"

OLD_RELEASE="$(readlink -f "$INSTALL_ROOT/current")"
OLD_VERSION="$(tr -d '\r\n' < "$OLD_RELEASE/VERSION")"
NEW_VERSION="$(tr -d '\r\n' < "$PACKAGE/VERSION")"
NEW_RELEASE="$INSTALL_ROOT/releases/$NEW_VERSION"
[[ "$NEW_VERSION" != "$OLD_VERSION" ]] || die "package version $NEW_VERSION is already installed"
[[ ! -e "$NEW_RELEASE" ]] || die "release directory already exists: $NEW_RELEASE"

BACKUP_ID="$(backup_instance "$INSTALL_ROOT" "$INSTANCE" "$OLD_VERSION")"
log "backup created: $BACKUP_ID"

ROLLBACK_ATTEMPTED=0
UPGRADE_COMPLETE=0
cleanup_upgrade() {
  local status=$?
  trap - EXIT
  if (( status != 0 && UPGRADE_COMPLETE == 0 && ROLLBACK_ATTEMPTED == 0 )); then
    ROLLBACK_ATTEMPTED=1
    log "upgrade failed; rolling back from backup $BACKUP_ID"
    local rollback_script="$OLD_RELEASE/wsl/rollback.sh"
    if [[ ! -f "$rollback_script" ]]; then
      rollback_script="$PACKAGE/wsl/rollback.sh"
    fi
    if [[ -f "$rollback_script" ]]; then
      bash "$rollback_script" \
        --install-root "$INSTALL_ROOT" \
        --target-user "$TARGET_USER" \
        --backup-id "$BACKUP_ID" || log "rollback also failed; manual recovery may be required"
    else
      log "rollback script is missing; manual recovery may be required"
    fi
  fi
  exit "$status"
}
trap cleanup_upgrade EXIT

log "stopping current containers"
compose "$TARGET_USER" "$INSTALL_ROOT" "$INSTANCE/.env" down --remove-orphans || true

mkdir -p "$NEW_RELEASE"
tar -C "$PACKAGE" \
  --exclude='./_staging' \
  --exclude='./.git' \
  --exclude='./backups' \
  --exclude='./*.zip' \
  --exclude='./*.sha256' \
  -cf - . | tar -C "$NEW_RELEASE" -xf -

python3 "$NEW_RELEASE/wsl/payload_merge.py" --package "$NEW_RELEASE" --instance "$INSTANCE"
python3 "$NEW_RELEASE/wsl/config_tool.py" \
  --mode configure \
  --instance "$INSTANCE" \
  --package "$NEW_RELEASE"

ln -sfn "releases/$NEW_VERSION" "$INSTALL_ROOT/current"
chown -R "$TARGET_USER:$TARGET_USER" "$INSTANCE" "$NEW_RELEASE"
chmod 600 "$INSTANCE/.env" "$INSTANCE/config/"*.toml "$INSTANCE/napcat/config/"*.json

if ! compose "$TARGET_USER" "$INSTALL_ROOT" "$INSTANCE/.env" up -d --build; then
  die "upgrade failed while starting containers"
fi

if ! wait_for_health qqbridge-maibot 240 || ! wait_for_health qqbridge-napcat 180; then
  die "upgrade health checks failed"
fi

cat > "$INSTANCE/upgrade-report.json" <<EOF
{
  "from_version": "$OLD_VERSION",
  "to_version": "$NEW_VERSION",
  "backup_id": "$BACKUP_ID",
  "completed_at_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
chown "$TARGET_USER:$TARGET_USER" "$INSTANCE/upgrade-report.json"
chmod 600 "$INSTANCE/upgrade-report.json"
UPGRADE_COMPLETE=1
prune_backups "$INSTALL_ROOT" 3
log "upgrade complete: $OLD_VERSION -> $NEW_VERSION"
