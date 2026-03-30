# Technology Stack — OS-APOW (workflow-orchestration-service)

## Languages

| Language | Version | Role |
|----------|---------|------|
| Python | 3.12+ | Primary — Sentinel orchestrator, FastAPI webhook notifier, models, interfaces |
| PowerShell Core (pwsh) | 7.x | Shell bridge scripts, auth synchronization, validation, CI helpers |
| Bash | 5.x | DevContainer lifecycle scripts, prompt assembly, shell bridge |

## Frameworks & Libraries

| Package | Purpose |
|---------|---------|
| FastAPI | Async webhook receiver (Work Event Notifier / "The Ear") |
| Uvicorn | ASGI server for FastAPI in production |
| Pydantic | Data validation, settings management, WorkItem/TaskType schemas |
| HTTPX | Async HTTP client for GitHub REST API calls from the Sentinel |

## Package Management & Build

| Tool | Purpose |
|------|---------|
| uv | Python package installer and dependency resolver (Rust-based) |
| Docker / DevContainers | Worker execution engine — sandboxed, environment-consistent containers |
| Docker Compose | Multi-container orchestration for complex task environments |

## AI / Agent Runtime

| Tool | Purpose |
|------|---------|
| opencode CLI | Agent runtime — runs agents defined in `.opencode/agents/` with MCP server support |
| ZhipuAI GLM models (glm-5, glm-4.7) | Primary LLM provider for orchestration |
| Kimi/Moonshot models (kimi-k2-thinking) | Alternative LLM provider |
| OpenAI models (gpt-5.4) | Alternative LLM provider |
| Google Gemini models | Alternative LLM provider |

## Infrastructure & CI/CD

| Component | Technology |
|-----------|-----------|
| CI/CD | GitHub Actions — orchestrator-agent workflow, validate workflow |
| Container Registry | GHCR (ghcr.io/intel-agency/workflow-orchestration-prebuild) |
| DevContainer Image | Prebuilt from `intel-agency/workflow-orchestration-prebuild` repo |
| Version Control | Git + GitHub |
| Project Management | GitHub Issues, Labels, Milestones, Projects (V2) |

## MCP Servers

| Server | Status | Purpose |
|--------|--------|---------|
| `@modelcontextprotocol/server-sequential-thinking` | Enabled | Structured reasoning for agent planning |
| `@modelcontextprotocol/server-memory` | Enabled | Knowledge graph persistence across sessions |
| `@modelcontextprotocol/server-github` | Disabled | GitHub API access (reserved for future use) |

## Testing

| Tool | Purpose |
|------|---------|
| Pester (pwsh) | PowerShell test framework for workflow and script validation |
| Bash test scripts | Shell-based integration tests (prompt assembly, devcontainer tools, image tags) |
| actionlint | GitHub Actions workflow linter |
| shellcheck | Shell script static analysis |
| gitleaks | Secret scanning |
| markdownlint | Markdown style enforcement |
