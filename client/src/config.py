"""
Centralized configuration for the OS-APOW Orchestration Client.

All values are sourced from environment variables with sensible defaults.
No secrets are hardcoded.
"""

import os


# --- Server Connection ---
OPENCODE_SERVER_URL = os.getenv("OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
OPENCODE_SERVER_DIR = os.getenv("OPENCODE_SERVER_DIR", "/opt/orchestration")

# --- GitHub ---
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_ORG = os.getenv("GITHUB_ORG", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "")

# --- Sentinel ---
SENTINEL_BOT_LOGIN = os.getenv("SENTINEL_BOT_LOGIN", "")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))
MAX_BACKOFF = int(os.getenv("MAX_BACKOFF", "960"))
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "300"))
SUBPROCESS_TIMEOUT = int(os.getenv("SUBPROCESS_TIMEOUT", "5700"))

# --- Webhook ---
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8000"))

# --- Shell Bridge ---
SHELL_BRIDGE_PATH = os.getenv(
    "SHELL_BRIDGE_PATH",
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "scripts",
        "devcontainer-opencode.sh",
    ),
)
