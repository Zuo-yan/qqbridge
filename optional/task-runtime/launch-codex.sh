#!/bin/sh
set -eu
exec docker run --rm -i --name "qqbridge-code-${CODEX_TASK_JOB_ID}" --network qqbridge-code-workers \
  --memory=384m --cpus=0.5 --pids-limit=96 --read-only --cap-drop=ALL --security-opt=no-new-privileges \
  --tmpfs /tmp:rw,nosuid,size=128m --tmpfs /root/.codex:rw,nosuid,size=48m \
  -v "${CODEX_TASK_WORKSPACE}:/work:rw" \
  -v "/root/qqbridge/experiments/codex-flash-20261106/.venv-sdk/lib/python3.12/site-packages/codex_cli_bin:/opt/codex:ro" -e CODEX_TASK_GATEWAY_TOKEN \
  --entrypoint /opt/codex/bin/codex qqbridge-codex-worker:0.1.0 "$@"
