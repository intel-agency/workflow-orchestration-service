# Orchestration client image — Python package with FastAPI placeholder endpoint.
# Phase 3 will wire the live webhook handler; this image reserves port 8000.
FROM python:3.12-slim

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# ── uv (Python package manager) ─────────────────────────────────────
COPY --from=ghcr.io/astral-sh/uv:0.10.9 /uv /usr/local/bin/uv

WORKDIR /app

# ── Install the client package ───────────────────────────────────────
COPY pyproject.toml ./
COPY src/ ./src/

RUN uv pip install --system --no-cache -e .

# ── Entrypoint ───────────────────────────────────────────────────────
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
