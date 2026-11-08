FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends git nodejs ca-certificates bash coreutils && rm -rf /var/lib/apt/lists/*
ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /work
LABEL local.qqbridge.codex-task-worker.version="0.1.0"
