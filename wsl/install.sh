#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

PACKAGE=""
INSTALL_ROOT=""
ANSWERS=""
TARGET_USER=""
NAPCAT_UID="1000"
NAPCAT_GID="1000"
PLATFORM="wsl"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --package) PACKAGE="$2"; shift 2 ;;
    --install-root) INSTALL_ROOT="$2"; shift 2 ;;
    --answers) ANSWERS="$2"; shift 2 ;;
    --target-user) TARGET_USER="$2"; shift 2 ;;
    --napcat-uid) NAPCAT_UID="$2"; shift 2 ;;
    --napcat-gid) NAPCAT_GID="$2"; shift 2 ;;
    --platform) PLATFORM="$2"; shift 2 ;;
    *) die "unknown argument: $1" ;;
  esac
done

[[ -n "$PACKAGE" && -n "$INSTALL_ROOT" && -n "$TARGET_USER" ]] || die "package, install root and target user are required"
case "$PLATFORM" in wsl|linux) ;; *) die "platform must be wsl or linux" ;; esac
[[ -f "$PACKAGE/VERSION" ]] || die "invalid package directory"
id "$TARGET_USER" >/dev/null 2>&1 || die "target user does not exist: $TARGET_USER"

TARGET_HOME="$(target_home "$TARGET_USER")"
case "$INSTALL_ROOT" in
  "~") INSTALL_ROOT="$TARGET_HOME" ;;
  "~/"*) INSTALL_ROOT="$TARGET_HOME/${INSTALL_ROOT#\~/}" ;;
esac
assert_absolute_path "$INSTALL_ROOT"

VERSION="$(tr -d '\r\n' < "$PACKAGE/VERSION")"
RELEASE="$INSTALL_ROOT/releases/$VERSION"
INSTANCE="$INSTALL_ROOT/instances/default"

if [[ -e "$INSTALL_ROOT/current" || -L "$INSTALL_ROOT/current" || -e "$INSTANCE/config/bot_config.toml" ]]; then
  die "an existing instance was found under $INSTALL_ROOT; use a configure or upgrade entrypoint instead"
fi

log "checking Docker Linux engine"
as_target "$TARGET_USER" docker info >/dev/null 2>&1 || die "Docker Linux engine is not available to target user $TARGET_USER"
if as_target "$TARGET_USER" docker inspect qqbridge-maibot >/dev/null 2>&1 \
  || as_target "$TARGET_USER" docker inspect qqbridge-napcat >/dev/null 2>&1; then
  die "QQBridge containers already exist; use a configure or upgrade entrypoint instead"
fi

log "installing release $VERSION into $RELEASE"
mkdir -p "$INSTALL_ROOT/releases" "$INSTALL_ROOT/instances" "$INSTALL_ROOT/backups"
mkdir -p "$RELEASE"
tar -C "$PACKAGE" \
  --exclude='./_staging' \
  --exclude='./.git' \
  --exclude='./backups' \
  --exclude='./*.zip' \
  --exclude='./*.sha256' \
  -cf - . | tar -C "$RELEASE" -xf -

mkdir -p \
  "$INSTANCE/config" \
  "$INSTANCE/plugins" \
  "$INSTANCE/data" \
  "$INSTANCE/logs" \
  "$INSTANCE/depends-data" \
  "$INSTANCE/personas" \
  "$INSTANCE/napcat/config" \
  "$INSTANCE/napcat/ntqq"

cp -a "$PACKAGE/payload/plugins/." "$INSTANCE/plugins/"
cp -a "$PACKAGE/payload/data/." "$INSTANCE/data/"
cp -a "$PACKAGE/payload/personas/." "$INSTANCE/personas/"

python3 "$RELEASE/wsl/config_tool.py" \
  --mode install \
  --instance "$INSTANCE" \
  --package "$RELEASE" \
  ${ANSWERS:+--answers "$ANSWERS"} \
  --napcat-uid "$NAPCAT_UID" \
  --napcat-gid "$NAPCAT_GID"

ln -sfn "releases/$VERSION" "$INSTALL_ROOT/current"
chown -R "$TARGET_USER:$TARGET_USER" "$INSTALL_ROOT"
chmod 700 "$INSTALL_ROOT" "$INSTALL_ROOT/instances" "$INSTANCE"
chmod 600 "$INSTANCE/.env" "$INSTANCE/config/"*.toml "$INSTANCE/napcat/config/"*.json

log "building patched MaiBot image and starting containers"
if ! compose "$TARGET_USER" "$INSTALL_ROOT" "$INSTANCE/.env" up -d --build; then
  die "container startup failed; inspect logs with: docker compose --env-file $INSTANCE/.env -f $RELEASE/compose.yaml logs"
fi

wait_for_health qqbridge-maibot 240 || die "MaiBot did not become healthy"
wait_for_health qqbridge-napcat 180 || die "NapCat did not become healthy"

if [[ "$PLATFORM" == "linux" ]]; then
  CONFIGURE_COMMAND="./configure-linux.sh --discover-groups"
  VERIFY_COMMAND="./verify-linux.sh"
else
  CONFIGURE_COMMAND="powershell -ExecutionPolicy Bypass -File configure.ps1 -DiscoverGroups"
  VERIFY_COMMAND="powershell -ExecutionPolicy Bypass -File verify.ps1"
fi

cat > "$INSTANCE/install-report.json" <<EOF
{
  "package_version": "$VERSION",
  "platform": "$PLATFORM",
  "installed_at_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "install_root": "$INSTALL_ROOT",
  "release": "$RELEASE",
  "instance": "$INSTANCE",
  "containers": ["qqbridge-maibot", "qqbridge-napcat"],
  "next_steps": [
    "Open the NapCat WebUI and scan the QQ login QR code.",
    "Run $CONFIGURE_COMMAND after login to set group and private allowlists.",
    "Run $VERIFY_COMMAND for a full health report."
  ]
}
EOF
chown "$TARGET_USER:$TARGET_USER" "$INSTANCE/install-report.json"
chmod 600 "$INSTANCE/install-report.json"

log "installation complete"
log "instance: $INSTANCE"
log "current release: $INSTALL_ROOT/current"
