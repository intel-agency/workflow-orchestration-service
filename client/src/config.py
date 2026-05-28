"""
Centralized configuration for the OS-APOW Orchestration Client.

All values are sourced from environment variables with sensible defaults.
No secrets are hardcoded.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def _safe_int(env_name: str, default: int) -> int:
    """Parse an environment variable as int, falling back to *default* on any parse error.

    If the variable is set to a non-integer value a structured WARN log is emitted
    so the operator knows which variable is mis-configured and what value is being
    substituted instead.
    """
    raw = os.getenv(env_name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (ValueError, TypeError) as exc:
        logger.warning(
            "Config: %s=%r is not a valid integer; using default=%d (%s)",
            env_name,
            raw,
            default,
            exc,
        )
        return default


# --- Server Connection ---
# Default URL uses the mission host port (14096) per the standalone architecture.
OPENCODE_SERVER_URL: str = os.getenv("OPENCODE_SERVER_URL", "http://127.0.0.1:14096")
# OPENCODE_SERVER_DIR defers entirely to the environment — no hardcoded fallback.
OPENCODE_SERVER_DIR: Optional[str] = os.getenv("OPENCODE_SERVER_DIR")

# --- GitHub ---
GITHUB_TOKEN: Optional[str] = os.getenv("GITHUB_TOKEN")
GITHUB_ORG: Optional[str] = os.getenv("GITHUB_ORG")
GITHUB_REPO: Optional[str] = os.getenv("GITHUB_REPO")

# --- Sentinel ---
SENTINEL_BOT_LOGIN: str = os.getenv("SENTINEL_BOT_LOGIN", "")
POLL_INTERVAL: int = _safe_int("POLL_INTERVAL", 60)
MAX_BACKOFF: int = _safe_int("MAX_BACKOFF", 960)
HEARTBEAT_INTERVAL: int = _safe_int("HEARTBEAT_INTERVAL", 300)
SUBPROCESS_TIMEOUT: int = _safe_int("SUBPROCESS_TIMEOUT", 5700)

# --- Webhook ---
WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "")
WEBHOOK_PORT: int = _safe_int("WEBHOOK_PORT", 8000)

# --- Shell Bridge ---
# Default: resolve relative to this file (client/src/config.py → client/scripts/devcontainer-opencode.sh).
# Override at runtime by setting the SHELL_BRIDGE_PATH environment variable.
SHELL_BRIDGE_PATH: str = os.getenv(
    "SHELL_BRIDGE_PATH",
    os.path.normpath(
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..",
            "scripts",
            "devcontainer-opencode.sh",
        )
    ),
)
