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
RESUME=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --package) PACKAGE="$2"; shift 2 ;;
    --install-root) INSTALL_ROOT="$2"; shift 2 ;;
    --answers) ANSWERS="$2"; shift 2 ;;
    --target-user) TARGET_USER="$2"; shift 2 ;;
    --napcat-uid) NAPCAT_UID="$2"; shift 2 ;;
    --napcat-gid) NAPCAT_GID="$2"; shift 2 ;;
    --platform) PLATFORM="$2"; shift 2 ;;
    --resume) RESUME=1; shift ;;
    *) die "unknown argument: $1" ;;
  esac
done

[[ -n "$PACKAGE" && -n "$INSTALL_ROOT" && -n "$TARGET_USER" ]] || die "package, install root and target user are required"
case "$PLATFORM" in wsl|linux) ;; *) die "platform must be wsl or linux" ;; esac
[[ -f "$PACKAGE/VERSION" ]] || die "invalid package directory"
id "$TARGET_USER" >/dev/null 2>&1 || die "target user does not exist: $TARGET_USER"
TARGET_GROUP="$(id -gn "$TARGET_USER")"
TARGET_HOME="$(target_home "$TARGET_USER")"
case "$INSTALL_ROOT" in
  "~") INSTALL_ROOT="$TARGET_HOME" ;;
  "~/"*) INSTALL_ROOT="$TARGET_HOME/${INSTALL_ROOT#\~/}" ;;
esac
assert_absolute_path "$INSTALL_ROOT"
INSTALL_ROOT="$(realpath -m "$INSTALL_ROOT")"
VERSION="$(tr -d '\r\n' < "$PACKAGE/VERSION")"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "invalid package version"
RELEASE="$INSTALL_ROOT/releases/$VERSION"
INSTANCE="$INSTALL_ROOT/instances/default"
PROGRESS="$INSTANCE/install-progress.json"

write_progress() {
  python3 -I - "$PROGRESS" "$1" "$VERSION" "$PLATFORM" "$INSTALL_ROOT" "$RELEASE" "$TARGET_USER" <<'PY'
import json, os, sys, tempfile
from pathlib import Path
path = Path(sys.argv[1])
record = dict(zip(("phase", "package_version", "platform", "install_root", "release", "target_user"), sys.argv[2:]))
record["schema_version"] = 1
fd, temporary = tempfile.mkstemp(prefix=".install-progress-", dir=path.parent)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")
    os.replace(temporary, path)
finally:
    Path(temporary).unlink(missing_ok=True)
PY
  chown "$TARGET_USER:$TARGET_GROUP" "$PROGRESS"
}

if (( RESUME )); then
  python3 -I - "$PROGRESS" "$VERSION" "$PLATFORM" "$INSTALL_ROOT" "$RELEASE" "$TARGET_USER" <<'PY'
import json, stat, sys
from pathlib import Path
path = Path(sys.argv[1])
try:
    record = json.loads(path.read_text(encoding="utf-8"))
    expected = dict(zip(("package_version", "platform", "install_root", "release", "target_user"), sys.argv[2:]))
    root, release = Path(sys.argv[4]), Path(sys.argv[5])
    instance = path.parent
    valid = (not path.is_symlink() and stat.S_IMODE(path.stat().st_mode) == 0o600
             and record.get("phase") in {"ready_to_start", "complete"}
             and all(record.get(key) == value for key, value in expected.items())
             and (root / "current").is_symlink()
             and (root / "current").resolve() == release.resolve()
             and (release / "VERSION").read_text().strip() == sys.argv[2]
             and all((instance / name).is_file() for name in
                     (".env", "config/bot_config.toml", "config/model_config.toml")))
except (OSError, ValueError, AttributeError):
    valid = False
if not valid:
    raise SystemExit("ERROR: resume requires a ready_to_start or complete marker and matching package, release, user, platform and generated configuration; existing files were preserved")
PY
else
  if [[ -e "$INSTALL_ROOT/current" || -L "$INSTALL_ROOT/current" || -e "$INSTANCE" || -L "$INSTANCE" || -e "$RELEASE" || -L "$RELEASE" ]]; then
    die "existing installation files found under $INSTALL_ROOT; files were preserved. Use --resume only for ready_to_start, otherwise recover manually or select a new empty install root"
  fi
fi

log "checking Docker Linux engine"
as_target "$TARGET_USER" docker info >/dev/null 2>&1 || die "Docker Linux engine is not available to target user $TARGET_USER"
if (( RESUME == 0 )); then
  if as_target "$TARGET_USER" docker inspect qqbridge-maibot >/dev/null 2>&1 \
    || as_target "$TARGET_USER" docker inspect qqbridge-napcat >/dev/null 2>&1; then
    die "QQBridge containers already exist; use a configure or upgrade entrypoint instead"
  fi
fi

READY=$RESUME
install_exit() {
  local status=$?
  if (( status != 0 )); then
    if (( READY )); then
      log "Installation files were preserved at ready_to_start. Retry this same package and context with --resume."
    else
      log "Installation stopped before ready_to_start. Files were preserved; automatic resume is unavailable. Recover manually or select a new empty install root."
    fi
  fi
}
trap install_exit EXIT

if (( RESUME == 0 )); then
  log "installing release $VERSION into $RELEASE"
  mkdir -p "$INSTALL_ROOT/releases" "$INSTALL_ROOT/instances" "$INSTALL_ROOT/backups"
  mkdir -m 700 "$INSTANCE"
  write_progress preparing
  mkdir "$RELEASE"
  tar -C "$PACKAGE" \
    --exclude='./_staging' --exclude='./.git' --exclude='./backups' \
    --exclude='./*.zip' --exclude='./*.sha256' \
    -cf - . | tar -C "$RELEASE" -xf -

  mkdir -p "$INSTANCE/config" "$INSTANCE/plugins" "$INSTANCE/data" \
    "$INSTANCE/logs" "$INSTANCE/depends-data" "$INSTANCE/personas" \
    "$INSTANCE/napcat/config" "$INSTANCE/napcat/ntqq"
  cp -a "$PACKAGE/payload/plugins/." "$INSTANCE/plugins/"
  cp -a "$PACKAGE/payload/data/." "$INSTANCE/data/"
  cp -a "$PACKAGE/payload/personas/." "$INSTANCE/personas/"

  python3 "$RELEASE/wsl/config_tool.py" \
    --mode install --instance "$INSTANCE" --package "$RELEASE" \
    ${ANSWERS:+--answers "$ANSWERS"} \
    --napcat-uid "$NAPCAT_UID" --napcat-gid "$NAPCAT_GID"

  ln -s "releases/$VERSION" "$INSTALL_ROOT/current"
  chown -R "$TARGET_USER:$TARGET_GROUP" "$INSTALL_ROOT"
  chmod 700 "$INSTALL_ROOT" "$INSTALL_ROOT/instances" "$INSTANCE"
  secure_instance_files "$INSTANCE"
  write_progress ready_to_start
  READY=1
fi

log "building patched MaiBot image and starting containers"
compose "$TARGET_USER" "$INSTALL_ROOT" "$INSTANCE/.env" up -d --build || die "container startup failed"
wait_for_health qqbridge-maibot 240 || die "MaiBot did not become healthy"
wait_for_health qqbridge-napcat 180 || die "NapCat did not become healthy"
# Startup may create new WebUI credential files after the initial permission pass.
secure_instance_files "$INSTANCE"

python3 -I - "$INSTANCE/install-report.json" "$VERSION" "$PLATFORM" "$INSTALL_ROOT" "$RELEASE" "$INSTANCE" <<'PY'
import datetime, json, os, sys
from pathlib import Path
path = Path(sys.argv[1])
version, platform, root, release, instance = sys.argv[2:]
configure = "./configure-linux.sh --discover-groups" if platform == "linux" else "powershell -ExecutionPolicy Bypass -File configure.ps1 -DiscoverGroups"
verify = "./verify-linux.sh" if platform == "linux" else "powershell -ExecutionPolicy Bypass -File verify.ps1"
report = {"package_version": version, "platform": platform,
          "installed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
          "install_root": root, "release": release, "instance": instance,
          "containers": ["qqbridge-maibot", "qqbridge-napcat"],
          "next_steps": ["Open the NapCat WebUI and scan the QQ login QR code.",
                         f"Run {configure} after login to set group and private allowlists.",
                         f"Run {verify} for a full health report."]}
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as stream:
    json.dump(report, stream, indent=2)
    stream.write("\n")
PY
chown "$TARGET_USER:$TARGET_GROUP" "$INSTANCE/install-report.json"
chmod 600 "$INSTANCE/install-report.json"
write_progress complete
trap - EXIT
log "installation complete"
log "instance: $INSTANCE"
log "current release: $INSTALL_ROOT/current"
