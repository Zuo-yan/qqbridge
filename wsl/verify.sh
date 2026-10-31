#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

INSTALL_ROOT=""
INSTANCE_NAME="default"
TARGET_USER=""
REQUIRE_LOGIN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-root) INSTALL_ROOT="$2"; shift 2 ;;
    --instance) INSTANCE_NAME="$2"; shift 2 ;;
    --target-user) TARGET_USER="$2"; shift 2 ;;
    --require-login) REQUIRE_LOGIN=1; shift ;;
    *) die "unknown argument: $1" ;;
  esac
done
[[ -n "$INSTALL_ROOT" && -n "$TARGET_USER" ]] || die "install root and target user are required"
assert_absolute_path "$INSTALL_ROOT"
[[ "$INSTANCE_NAME" =~ ^[A-Za-z0-9_-]+$ ]] || die "invalid instance name"
INSTANCE="$INSTALL_ROOT/instances/$INSTANCE_NAME"
ENV_FILE="$INSTANCE/.env"
CURRENT="$INSTALL_ROOT/current"
RELEASE="$(readlink -f "$CURRENT" 2>/dev/null || true)"
failures=0
warnings=0
check() {
  local label="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    printf 'PASS  %s\n' "$label"
  else
    printf 'FAIL  %s\n' "$label"
    failures=$((failures + 1))
  fi
}
warn_check() {
  local label="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    printf 'PASS  %s\n' "$label"
  else
    printf 'WARN  %s\n' "$label"
    warnings=$((warnings + 1))
  fi
}
check "current release symlink" test -L "$CURRENT"
check "current release metadata" test -f "$RELEASE/manifest.json"
check "instance environment" test -f "$ENV_FILE"
check "bot configuration" test -f "$INSTANCE/config/bot_config.toml"
check "model configuration" test -f "$INSTANCE/config/model_config.toml"
check "adapter policy" test -f "$INSTANCE/config/adapter_policy.toml"
check "NapCat WebUI configuration" test -f "$INSTANCE/napcat/config/webui.json"
check "OneBot configuration" test -f "$INSTANCE/napcat/config/onebot11.json"
check "persona manager seed" test -f "$INSTANCE/plugins/persona-manager/seed.json"
check "emoji resources" test -d "$INSTANCE/data/emoji"
check ".env permissions 600" test "$(stat -c '%a' "$ENV_FILE" 2>/dev/null || echo 000)" = "600"

# Inspect metadata only; never print configuration values or credentials.
if python3 -I - "$INSTANCE" "$RELEASE" <<'PY'
import json, stat, sys
from pathlib import Path
instance, release = map(Path, sys.argv[1:])
errors = 0
def result(label, valid):
    global errors
    print(f"{'PASS' if valid else 'FAIL'}  {label}")
    errors += not valid
try:
    files = set()
    for directory, pattern in (("config", "*.toml"), ("napcat/config", "*.json"),
                               ("plugins", "config.toml")):
        base = instance / directory
        files.update(base.rglob(pattern))
    for base in (instance / "data", instance / "plugins"):
        if base.is_dir():
            files.update(path for path in base.rglob("*")
                         if path.is_file() and ("webui" in path.name.lower()
                         or path.name.lower() in {"credentials.json", "token.json", "tokens.json", "auth.json"}))
    for path in sorted(files):
        result(f"private file mode 600: {path.relative_to(instance)}",
               not path.is_symlink() and stat.S_IMODE(path.stat().st_mode) == 0o600)
    metadata = json.loads((release / "manifest.json").read_text(encoding="utf-8"))
    plugins = metadata["plugins"]
    names = [item["name"] for item in plugins]
    valid = bool(names) and all(isinstance(name, str) and name not in {".", ".."}
                              and "/" not in name and "\\" not in name for name in names)
    result("package plugin metadata", valid)
    if valid:
        for name in names:
            result(f"expected plugin: {name}", (instance / "plugins" / name).is_dir())
except (OSError, ValueError, KeyError, TypeError):
    result("permission and plugin metadata inspection", False)
raise SystemExit(1 if errors else 0)
PY
then
  :
else
  failures=$((failures + 1))
fi

check "Docker Linux engine" as_target "$TARGET_USER" docker info
if [[ -n "$RELEASE" && -f "$ENV_FILE" ]]; then
  check "Compose configuration" compose "$TARGET_USER" "$INSTALL_ROOT" "$ENV_FILE" config --quiet
fi
for container in qqbridge-maibot qqbridge-napcat; do
  status="$(as_target "$TARGET_USER" docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container" 2>/dev/null || true)"
  check "$container healthy/running" test "$status" = "healthy" -o "$status" = "running"
done
login_check() {
  python3 -I - "$RELEASE/wsl/onebot.py" "$INSTANCE" <<'PY'
import json, subprocess, sys
try:
    response = subprocess.run([sys.executable, sys.argv[1], "--instance", sys.argv[2],
                               "--action", "get_login_info"], capture_output=True, text=True, timeout=45)
    data = json.loads(response.stdout) if response.returncode == 0 else None
    valid = isinstance(data, dict) and str(data.get("user_id", "")).isdigit() and int(data["user_id"]) > 0
except (OSError, ValueError, subprocess.TimeoutExpired):
    valid = False
raise SystemExit(0 if valid else 1)
PY
}
if (( REQUIRE_LOGIN )); then
  check "OneBot login info (required)" login_check
else
  warn_check "OneBot login info" login_check
fi
printf 'SUMMARY failures=%s warnings=%s\n' "$failures" "$warnings"
if (( failures > 0 )); then
  exit 1
fi
