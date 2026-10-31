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

TARGET_GROUP="$(id -gn "$TARGET_USER")"
log "stopping current containers before backup"
if ! compose "$TARGET_USER" "$INSTALL_ROOT" "$INSTANCE/.env" stop; then
  compose "$TARGET_USER" "$INSTALL_ROOT" "$INSTANCE/.env" up -d || true
  die "could not stop current containers; backup and upgrade were not started"
fi
if ! BACKUP_ID="$(backup_instance "$INSTALL_ROOT" "$INSTANCE" "$OLD_VERSION")"; then
  log "backup failed; restarting the unchanged current release"
  compose "$TARGET_USER" "$INSTALL_ROOT" "$INSTANCE/.env" up -d || log "restart failed; start the current release manually"
  die "backup failed; upgrade was not started and partial backup files were preserved"
fi
log "backup created: $BACKUP_ID"

ROLLBACK_ATTEMPTED=0
UPGRADE_COMPLETE=0
cleanup_upgrade() {
  local status=$?
  trap - EXIT
  if (( status != 0 && UPGRADE_COMPLETE == 0 && ROLLBACK_ATTEMPTED == 0 )); then
    ROLLBACK_ATTEMPTED=1
    log "upgrade failed; rolling back from backup $BACKUP_ID"
    # Use this package's recovery implementation, including preservation fixes.
    local rollback_script="$PACKAGE/wsl/rollback.sh"
    if [[ ! -f "$rollback_script" ]]; then
      rollback_script="$OLD_RELEASE/wsl/rollback.sh"
    fi
    if [[ -f "$rollback_script" ]]; then
      if bash "$rollback_script" \
        --install-root "$INSTALL_ROOT" \
        --target-user "$TARGET_USER" \
        --backup-id "$BACKUP_ID"; then
        # Keep failed code for diagnosis while freeing its version path for retry.
        if [[ -d "$NEW_RELEASE" && "$(readlink -f "$INSTALL_ROOT/current")" == "$OLD_RELEASE" ]]; then
          local quarantine
          mkdir -p "$INSTALL_ROOT/recovery"
          quarantine="$(mktemp -d "$INSTALL_ROOT/recovery/failed-release-$NEW_VERSION-XXXXXX")"
          chmod 700 "$INSTALL_ROOT/recovery" "$quarantine"
          mv -- "$NEW_RELEASE" "$quarantine/release" || log "could not quarantine failed release; retry requires manual recovery"
          log "failed release preserved at $quarantine/release"
        fi
      else
        log "rollback also failed; manual recovery may be required"
      fi
    else
      log "rollback script is missing; manual recovery may be required"
    fi
  fi
  exit "$status"
}
trap cleanup_upgrade EXIT

log "stopping current containers"
compose "$TARGET_USER" "$INSTALL_ROOT" "$INSTANCE/.env" down --remove-orphans

mkdir "$NEW_RELEASE"
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
chown -R "$TARGET_USER:$TARGET_GROUP" "$INSTANCE" "$NEW_RELEASE"
secure_instance_files "$INSTANCE"

if ! compose "$TARGET_USER" "$INSTALL_ROOT" "$INSTANCE/.env" up -d --build; then
  die "upgrade failed while starting containers"
fi

if ! wait_for_health qqbridge-maibot 240 || ! wait_for_health qqbridge-napcat 180; then
  die "upgrade health checks failed"
fi
secure_instance_files "$INSTANCE"

cat > "$INSTANCE/upgrade-report.json" <<EOF
{
  "from_version": "$OLD_VERSION",
  "to_version": "$NEW_VERSION",
  "backup_id": "$BACKUP_ID",
  "completed_at_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
chown "$TARGET_USER:$TARGET_GROUP" "$INSTANCE/upgrade-report.json"
chmod 600 "$INSTANCE/upgrade-report.json"
UPGRADE_COMPLETE=1
prune_backups "$INSTALL_ROOT" 3
log "upgrade complete: $OLD_VERSION -> $NEW_VERSION"
