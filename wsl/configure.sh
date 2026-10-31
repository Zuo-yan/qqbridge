#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

PACKAGE=""
INSTALL_ROOT=""
ANSWERS=""
TARGET_USER=""
INSTANCE_NAME="default"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --package) PACKAGE="$2"; shift 2 ;;
    --install-root) INSTALL_ROOT="$2"; shift 2 ;;
    --answers) ANSWERS="$2"; shift 2 ;;
    --target-user) TARGET_USER="$2"; shift 2 ;;
    --instance) INSTANCE_NAME="$2"; shift 2 ;;
    *) die "unknown argument: $1" ;;
  esac
done

[[ -n "$PACKAGE" && -n "$INSTALL_ROOT" && -n "$TARGET_USER" ]] || die "package, install root and target user are required"
[[ "$INSTANCE_NAME" =~ ^[A-Za-z0-9_-]+$ ]] || die "invalid instance name: $INSTANCE_NAME"
INSTANCE="$INSTALL_ROOT/instances/$INSTANCE_NAME"
[[ -f "$INSTANCE/.env" ]] || die "instance not found: $INSTANCE"

python3 "$PACKAGE/wsl/config_tool.py" \
  --mode configure \
  --instance "$INSTANCE" \
  --package "$PACKAGE" \
  ${ANSWERS:+--answers "$ANSWERS"}

chown -R "$TARGET_USER:$TARGET_USER" "$INSTANCE"
chmod 600 "$INSTANCE/.env" "$INSTANCE/config/"*.toml "$INSTANCE/napcat/config/"*.json

log "applying configuration"
compose "$TARGET_USER" "$INSTALL_ROOT" "$INSTANCE/.env" up -d
wait_for_health qqbridge-maibot 180 || die "MaiBot did not become healthy after configuration"
wait_for_health qqbridge-napcat 120 || die "NapCat did not become healthy after configuration"
log "configuration applied"
