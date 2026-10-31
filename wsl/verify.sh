#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

INSTALL_ROOT=""
INSTANCE_NAME="default"
TARGET_USER=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-root) INSTALL_ROOT="$2"; shift 2 ;;
    --instance) INSTANCE_NAME="$2"; shift 2 ;;
    --target-user) TARGET_USER="$2"; shift 2 ;;
    *) die "unknown argument: $1" ;;
  esac
done

[[ -n "$INSTALL_ROOT" && -n "$TARGET_USER" ]] || die "install root and target user are required"
INSTANCE="$INSTALL_ROOT/instances/$INSTANCE_NAME"
ENV_FILE="$INSTANCE/.env"
CURRENT="$INSTALL_ROOT/current"
RELEASE="$(readlink -f "$CURRENT" 2>/dev/null || true)"
failures=0
warnings=0

check() {
  local label="$1"
  shift
  if "$@"; then
    printf 'PASS  %s\n' "$label"
  else
    printf 'FAIL  %s\n' "$label"
    failures=$((failures + 1))
  fi
}

warn_check() {
  local label="$1"
  shift
  if "$@"; then
    printf 'PASS  %s\n' "$label"
  else
    printf 'WARN  %s\n' "$label"
    warnings=$((warnings + 1))
  fi
}

check "current release symlink" test -n "$RELEASE"
check "instance environment" test -f "$ENV_FILE"
check "bot configuration" test -f "$INSTANCE/config/bot_config.toml"
check "model configuration" test -f "$INSTANCE/config/model_config.toml"
check "adapter policy" test -f "$INSTANCE/config/adapter_policy.toml"
check "NapCat WebUI configuration" test -f "$INSTANCE/napcat/config/webui.json"
check "OneBot configuration" test -f "$INSTANCE/napcat/config/onebot11.json"
check "persona manager seed" test -f "$INSTANCE/plugins/persona-manager/seed.json"
check "emoji resources" test -d "$INSTANCE/data/emoji"
check ".env permissions 600" test "$(stat -c '%a' "$ENV_FILE" 2>/dev/null || echo 000)" = "600"
check "Docker Linux engine" as_target "$TARGET_USER" docker info

if [[ -n "$RELEASE" && -f "$ENV_FILE" ]]; then
  check "Compose configuration" compose "$TARGET_USER" "$INSTALL_ROOT" "$ENV_FILE" config --quiet
fi

for container in qqbridge-maibot qqbridge-napcat; do
  status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container" 2>/dev/null || true)"
  check "$container status ($status)" test "$status" = "healthy" -o "$status" = "running"
done

warn_check "OneBot login info" python3 "$RELEASE/wsl/onebot.py" --instance "$INSTANCE" --action get_login_info

plugin_count="$(find "$INSTANCE/plugins" -mindepth 1 -maxdepth 1 -type d | wc -l)"
check "plugin count is at least 17 ($plugin_count)" test "$plugin_count" -ge 17

printf 'SUMMARY failures=%s warnings=%s\n' "$failures" "$warnings"
if (( failures > 0 )); then
  exit 1
fi
