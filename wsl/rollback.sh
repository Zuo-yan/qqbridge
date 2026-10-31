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
[[ "$BACKUP_ID" =~ ^[0-9TZ-]+$ ]] || die "invalid backup ID: $BACKUP_ID"
BACKUP_DIR="$INSTALL_ROOT/backups/$BACKUP_ID"
[[ -f "$BACKUP_DIR/instance.tar.gz" && -f "$BACKUP_DIR/metadata.env" ]] || die "backup is incomplete: $BACKUP_ID"

PREVIOUS_VERSION="$(awk -F= '$1 == "PREVIOUS_VERSION" { print substr($0, index($0, "=") + 1); exit }' "$BACKUP_DIR/metadata.env")"
[[ "$PREVIOUS_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "backup metadata has an invalid previous version"
OLD_RELEASE="$INSTALL_ROOT/releases/$PREVIOUS_VERSION"
[[ -f "$OLD_RELEASE/VERSION" ]] || die "previous release is missing: $OLD_RELEASE"

INSTANCE="$INSTALL_ROOT/instances/default"
ENV_FILE="$INSTANCE/.env"
if [[ -f "$ENV_FILE" && -e "$INSTALL_ROOT/current" ]]; then
  compose "$TARGET_USER" "$INSTALL_ROOT" "$ENV_FILE" down --remove-orphans || die "could not stop containers; instance files were preserved"
fi

log "restoring backup $BACKUP_ID"
mkdir -p "$INSTALL_ROOT/recovery"
RECOVERY="$(mktemp -d "$INSTALL_ROOT/recovery/rollback-$BACKUP_ID-XXXXXX")"
chmod 700 "$INSTALL_ROOT/recovery" "$RECOVERY"
mkdir "$RECOVERY/restored"
tar -C "$RECOVERY/restored" -xzf "$BACKUP_DIR/instance.tar.gz"
[[ -f "$RECOVERY/restored/default/config/bot_config.toml" && -f "$RECOVERY/restored/default/.env" ]] || die "restored instance is invalid; current instance was preserved"
if [[ -e "$INSTANCE" || -L "$INSTANCE" ]]; then
  mv -- "$INSTANCE" "$RECOVERY/previous-instance"
fi
if ! mv -- "$RECOVERY/restored/default" "$INSTANCE"; then
  if [[ -e "$RECOVERY/previous-instance" ]]; then
    mv -- "$RECOVERY/previous-instance" "$INSTANCE" || true
  fi
  die "could not activate restored instance; recovery files are at $RECOVERY"
fi
log "previous instance preserved at $RECOVERY/previous-instance"

ln -sfn "releases/$PREVIOUS_VERSION" "$INSTALL_ROOT/current"
TARGET_GROUP="$(id -gn "$TARGET_USER")"
chown -R "$TARGET_USER:$TARGET_GROUP" "$INSTANCE"
secure_instance_files "$INSTANCE"

compose "$TARGET_USER" "$INSTALL_ROOT" "$INSTANCE/.env" up -d --build
wait_for_health qqbridge-maibot 240 || die "MaiBot did not become healthy after rollback"
wait_for_health qqbridge-napcat 180 || die "NapCat did not become healthy after rollback"
secure_instance_files "$INSTANCE"
prune_backups "$INSTALL_ROOT" 3
log "rollback complete: restored version $PREVIOUS_VERSION from $BACKUP_ID"
