# Independent file task runtime (opt-in source snapshot)

The sources match the deployed 2026-11-08 integration. They use Codex SDK
0.167.0 through a local Responses-to-Vertex adapter with Flash MEDIUM. They
are not part of the default installer and do not contain auth or job data.

Deployment requires Linux, Docker, Python 3.12, a dedicated SDK venv, and
local credentials. Install requirements.txt into .venv-sdk under this directory;
build Worker.Dockerfile as qqbridge-codex-worker:0.1.0. The source currently
expects /root/qqbridge/experiments/codex-flash-20261106; either use that path
or review all path constants and launch-codex.sh before installing elsewhere.

Create the internal Docker network qqbridge-code-workers, configure gateway-ip.txt
with its host gateway, and generate distinct random gateway-token and broker-token
files (mode 600). Do not reuse the bot API key as either token. Run gateway
--help and task_broker.py --help for required arguments; bind only to Docker
internal gateways. Configure optional/plugins/code-tasks with the broker URL,
its token file and explicitly permitted group IDs. Share jobs at
/MaiMBot/data/code-tasks/jobs in the bot container. No service is auto-installed.

launch-codex.sh mounts only the current job, a read-only CLI and ephemeral
config. The worker has no host Docker socket or Google credentials. The trusted
host broker needs Docker access. Preserve its bounded queue and network limits.
Never mount personal Codex auth.json or the entire bot instance into a worker.

Chat uses its separate Argon/Flash/DeepSeek route. Files are delivered to the
original group with an @ to the requester. Only simple single-file work is
supported. PDF editing and full projects are not implemented.

This sync validates syntax/builds without submitting paid model tasks or sending
QQ messages. Installing these files alone is not an end-to-end acceptance test.
