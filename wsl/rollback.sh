#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

INSTALL_ROOT=""
TARGET_USER=""
BACKUP_ID=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-root) INSTALL_ROOT="$2"; shift 2 ;;
    --target-user) TARGET_USER="$2"; shift 2 ;;
    --backup-id) BACKUP_ID="$2"; shift 2 ;;
    *) die "unknown argument: $1" ;;
  esac
done

[[ -n "$INSTALL_ROOT" && -n "$TARGET_USER" ]] || die "install root and target user are required"
if [[ -z "$BACKUP_ID" ]]; then
  BACKUP_ID="$(find "$INSTALL_ROOT/backups" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -r | head -n 1)"
fi
[[ -n "$BACKUP_ID" ]] || die "no backup is available"
BACKUP_DIR="$INSTALL_ROOT/backups/$BACKUP_ID"
[[ -f "$BACKUP_DIR/instance.tar.gz" && -f "$BACKUP_DIR/metadata.env" ]] || die "backup is incomplete: $BACKUP_ID"

# shellcheck disable=SC1090
source "$BACKUP_DIR/metadata.env"
[[ -n "${PREVIOUS_VERSION:-}" ]] || die "backup metadata has no previous version"
OLD_RELEASE="$INSTALL_ROOT/releases/$PREVIOUS_VERSION"
[[ -f "$OLD_RELEASE/VERSION" ]] || die "previous release is missing: $OLD_RELEASE"

INSTANCE="$INSTALL_ROOT/instances/default"
ENV_FILE="$INSTANCE/.env"
if [[ -f "$ENV_FILE" && -e "$INSTALL_ROOT/current" ]]; then
  compose "$TARGET_USER" "$INSTALL_ROOT" "$ENV_FILE" down --remove-orphans || true
fi

log "restoring backup $BACKUP_ID"
case "$INSTANCE" in
  "$INSTALL_ROOT"/instances/default) ;;
  *) die "refusing unsafe instance path: $INSTANCE" ;;
esac
rm -rf -- "$INSTANCE"
tar -C "$INSTALL_ROOT/instances" -xzf "$BACKUP_DIR/instance.tar.gz"
[[ -f "$INSTANCE/config/bot_config.toml" ]] || die "restored instance is invalid"

ln -sfn "releases/$PREVIOUS_VERSION" "$INSTALL_ROOT/current"
chown -R "$TARGET_USER:$TARGET_USER" "$INSTANCE"
chmod 600 "$INSTANCE/.env" "$INSTANCE/config/"*.toml "$INSTANCE/napcat/config/"*.json

compose "$TARGET_USER" "$INSTALL_ROOT" "$INSTANCE/.env" up -d --build
wait_for_health qqbridge-maibot 240 || die "MaiBot did not become healthy after rollback"
wait_for_health qqbridge-napcat 180 || die "NapCat did not become healthy after rollback"
prune_backups "$INSTALL_ROOT" 3
log "rollback complete: restored version $PREVIOUS_VERSION from $BACKUP_ID"
