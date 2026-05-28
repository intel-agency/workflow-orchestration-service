# Orchestration server image — self-contained opencode serve runtime.
# All agents, commands, scripts, and configs ship at /opt/orchestration/.
FROM python:3.12-slim

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# ── System dependencies ──────────────────────────────────────────────
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        ca-certificates \
        curl \
        git \
        unzip \
    && rm -rf /var/lib/apt/lists/*

# ── Node.js LTS (required for npx / MCP server packages) ────────────
ARG NODE_VERSION=24.14.0
RUN curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.gz" \
        -o /tmp/node.tar.gz \
    && tar -xzf /tmp/node.tar.gz -C /usr/local --strip-components=1 \
    && rm /tmp/node.tar.gz \
    && node --version

# ── Bun ──────────────────────────────────────────────────────────────
ARG BUN_VERSION=1.3.10
RUN curl -fsSL "https://github.com/oven-sh/bun/releases/download/bun-v${BUN_VERSION}/bun-linux-x64.zip" \
        -o /tmp/bun.zip \
    && unzip -q /tmp/bun.zip -d /tmp \
    && mv /tmp/bun-linux-x64/bun /usr/local/bin/bun \
    && chmod +x /usr/local/bin/bun \
    && rm -rf /tmp/bun.zip /tmp/bun-linux-x64 \
    && bun --version

# ── uv (Python package manager) ─────────────────────────────────────
ARG UV_VERSION=0.10.9
RUN curl -fsSL "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-x86_64-unknown-linux-gnu.tar.gz" \
    | tar -xz -C /usr/local/bin --strip-components=1 \
    && uv --version

# ── GitHub CLI ───────────────────────────────────────────────────────
# hadolint ignore=DL3008
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install --no-install-recommends -y gh \
    && rm -rf /var/lib/apt/lists/* \
    && gh --version

# ── opencode CLI (npm package: opencode-ai) ─────────────────────────
ARG OPENCODE_VERSION=1.15.5
RUN npm install -g "opencode-ai@${OPENCODE_VERSION}" \
    && opencode --version

# ── Python runtime dependencies ─────────────────────────────────────
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# ── Orchestration root ───────────────────────────────────────────────
ENV ORCHESTRATION_ROOT=/opt/orchestration
RUN mkdir -p "${ORCHESTRATION_ROOT}/prompts"

COPY opencode.json "${ORCHESTRATION_ROOT}/"
COPY AGENTS.md "${ORCHESTRATION_ROOT}/"
COPY run_opencode_prompt.sh "${ORCHESTRATION_ROOT}/"
COPY .opencode/ "${ORCHESTRATION_ROOT}/.opencode/"
COPY scripts/ "${ORCHESTRATION_ROOT}/scripts/"
COPY .github/workflows/prompts/orchestrator-agent-prompt.md \
     "${ORCHESTRATION_ROOT}/prompts/orchestrator-agent-prompt.md"

# D1 enforcement: replace any remaining glm-5 default-model references
# with glm-4.7 inside the image (agent .md files still carry the old default).
RUN find "${ORCHESTRATION_ROOT}" -type f \
        \( -name '*.md' -o -name '*.sh' -o -name '*.json' -o -name '*.ps1' \) \
        -exec sed -i 's|zai-coding-plan/glm-5|zai-coding-plan/glm-4.7|g' {} + \
    && ! grep -r 'zai-coding-plan/glm-5' "${ORCHESTRATION_ROOT}"

# Ensure scripts are executable
RUN find "${ORCHESTRATION_ROOT}/scripts" -name '*.sh' -exec chmod +x {} + \
    && chmod +x "${ORCHESTRATION_ROOT}/run_opencode_prompt.sh"

WORKDIR /opt/orchestration

EXPOSE 4096

ENTRYPOINT ["/opt/orchestration/scripts/entrypoint.sh"]
