"""
Unit tests for client/src/config.py.

Coverage: defaults, env-var overrides, malformed-int fallback (VAL-CLI-010),
and missing-optional behaviour (VAL-CLI-003, VAL-CLI-011, VAL-CLI-012,
VAL-XCT-012).
"""

import importlib
import logging
import os

import pytest

import src.config as config_module


def _reload_config(monkeypatch, **env_overrides):
    """Clear all config-related env vars, apply *env_overrides*, then reload the module.

    Reloading is necessary because the module evaluates env vars at import time.
    """
    config_vars = [
        "OPENCODE_SERVER_URL",
        "OPENCODE_SERVER_DIR",
        "SHELL_BRIDGE_PATH",
        "GITHUB_TOKEN",
        "GITHUB_ORG",
        "GITHUB_REPO",
        "SENTINEL_BOT_LOGIN",
        "POLL_INTERVAL",
        "MAX_BACKOFF",
        "HEARTBEAT_INTERVAL",
        "SUBPROCESS_TIMEOUT",
        "WEBHOOK_SECRET",
        "WEBHOOK_PORT",
    ]
    for var in config_vars:
        monkeypatch.delenv(var, raising=False)
    for key, value in env_overrides.items():
        monkeypatch.setenv(key, value)

    importlib.reload(config_module)
    return config_module


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


class TestDefaults:
    """OPENCODE_SERVER_URL and integer vars use the mission-specified defaults."""

    def test_opencode_server_url_default_is_mission_host_port(self, monkeypatch):
        """Default OPENCODE_SERVER_URL must point to the mission host port 14096."""
        config = _reload_config(monkeypatch)
        assert config.OPENCODE_SERVER_URL == "http://127.0.0.1:14096"

    def test_opencode_server_dir_default_is_none(self, monkeypatch):
        """OPENCODE_SERVER_DIR has no hardcoded fallback — must be None when absent."""
        config = _reload_config(monkeypatch)
        assert config.OPENCODE_SERVER_DIR is None

    def test_poll_interval_default(self, monkeypatch):
        config = _reload_config(monkeypatch)
        assert config.POLL_INTERVAL == 60

    def test_max_backoff_default(self, monkeypatch):
        config = _reload_config(monkeypatch)
        assert config.MAX_BACKOFF == 960

    def test_heartbeat_interval_default(self, monkeypatch):
        config = _reload_config(monkeypatch)
        assert config.HEARTBEAT_INTERVAL == 300

    def test_subprocess_timeout_default(self, monkeypatch):
        config = _reload_config(monkeypatch)
        assert config.SUBPROCESS_TIMEOUT == 5700

    def test_webhook_port_default(self, monkeypatch):
        config = _reload_config(monkeypatch)
        assert config.WEBHOOK_PORT == 8000

    def test_shell_bridge_path_default_is_real_file(self, monkeypatch):
        """Default SHELL_BRIDGE_PATH must resolve to an existing file (VAL-CLI-011)."""
        config = _reload_config(monkeypatch)
        assert os.path.isfile(config.SHELL_BRIDGE_PATH), (
            f"SHELL_BRIDGE_PATH default {config.SHELL_BRIDGE_PATH!r} is not a file"
        )

    def test_shell_bridge_path_default_ends_with_correct_suffix(self, monkeypatch):
        """Default SHELL_BRIDGE_PATH must end with client/scripts/devcontainer-opencode.sh."""
        config = _reload_config(monkeypatch)
        assert config.SHELL_BRIDGE_PATH.endswith(
            os.path.join("client", "scripts", "devcontainer-opencode.sh")
        ), f"Unexpected SHELL_BRIDGE_PATH: {config.SHELL_BRIDGE_PATH!r}"


# ---------------------------------------------------------------------------
# Overrides
# ---------------------------------------------------------------------------


class TestOverrides:
    """Env-var values must take precedence over every default."""

    def test_opencode_server_url_override(self, monkeypatch):
        config = _reload_config(monkeypatch, OPENCODE_SERVER_URL="http://other:9000")
        assert config.OPENCODE_SERVER_URL == "http://other:9000"

    def test_opencode_server_dir_override(self, monkeypatch):
        config = _reload_config(monkeypatch, OPENCODE_SERVER_DIR="/opt/orchestration")
        assert config.OPENCODE_SERVER_DIR == "/opt/orchestration"

    def test_poll_interval_override(self, monkeypatch):
        config = _reload_config(monkeypatch, POLL_INTERVAL="30")
        assert config.POLL_INTERVAL == 30

    def test_heartbeat_interval_override(self, monkeypatch):
        config = _reload_config(monkeypatch, HEARTBEAT_INTERVAL="120")
        assert config.HEARTBEAT_INTERVAL == 120

    def test_shell_bridge_path_override(self, monkeypatch, tmp_path):
        fake_bridge = tmp_path / "bridge.sh"
        fake_bridge.write_text("#!/bin/sh\n")
        config = _reload_config(monkeypatch, SHELL_BRIDGE_PATH=str(fake_bridge))
        assert config.SHELL_BRIDGE_PATH == str(fake_bridge)

    def test_sentinel_bot_login_override(self, monkeypatch):
        config = _reload_config(monkeypatch, SENTINEL_BOT_LOGIN="mybot")
        assert config.SENTINEL_BOT_LOGIN == "mybot"


# ---------------------------------------------------------------------------
# Malformed-integer fallback (VAL-CLI-010, VAL-XCT-012)
# ---------------------------------------------------------------------------


class TestMalformedIntFallback:
    """Non-integer env-var values must NOT raise; they fall back to defaults with a WARN log."""

    def test_poll_interval_bad_value_falls_back(self, monkeypatch, caplog):
        """Setting POLL_INTERVAL to a non-integer must fall back to 60 (VAL-CLI-010)."""
        with caplog.at_level(logging.WARNING, logger="src.config"):
            config = _reload_config(monkeypatch, POLL_INTERVAL="not-a-number")
        assert config.POLL_INTERVAL == 60

    def test_poll_interval_bad_value_emits_warn_log(self, monkeypatch, caplog):
        """A WARN log mentioning POLL_INTERVAL must be emitted."""
        with caplog.at_level(logging.WARNING, logger="src.config"):
            _reload_config(monkeypatch, POLL_INTERVAL="not-a-number")
        assert any(
            "POLL_INTERVAL" in r.message for r in caplog.records
        ), "Expected a WARNING log record mentioning POLL_INTERVAL"

    def test_malformed_int_does_not_raise(self, monkeypatch):
        """Multiple malformed int env vars must never raise an exception."""
        config = _reload_config(
            monkeypatch,
            POLL_INTERVAL="abc",
            MAX_BACKOFF="xyz",
            HEARTBEAT_INTERVAL="!@#",
            SUBPROCESS_TIMEOUT="1.5",  # float — not a valid int
            WEBHOOK_PORT="nope",
        )
        assert config.POLL_INTERVAL == 60
        assert config.MAX_BACKOFF == 960
        assert config.HEARTBEAT_INTERVAL == 300
        assert config.SUBPROCESS_TIMEOUT == 5700
        assert config.WEBHOOK_PORT == 8000

    def test_heartbeat_interval_bad_value_falls_back(self, monkeypatch, caplog):
        with caplog.at_level(logging.WARNING, logger="src.config"):
            config = _reload_config(monkeypatch, HEARTBEAT_INTERVAL="bad")
        assert config.HEARTBEAT_INTERVAL == 300

    def test_warn_log_does_not_include_secret_values(self, monkeypatch, caplog):
        """The WARN log must not echo secret-shaped values (VAL-CLI-012 spirit).

        WEBHOOK_SECRET is a string var, so it never goes through _safe_int and
        should never appear in config-level log output.
        """
        with caplog.at_level(logging.WARNING, logger="src.config"):
            _reload_config(
                monkeypatch,
                POLL_INTERVAL="bad",
                WEBHOOK_SECRET="FAKE-WEBHOOK-SECRET-FOR-TESTING-XYZ",
            )
        for record in caplog.records:
            assert "FAKE-WEBHOOK-SECRET-FOR-TESTING-XYZ" not in record.getMessage()


# ---------------------------------------------------------------------------
# Missing-optional (no-default) vars
# ---------------------------------------------------------------------------


class TestMissingOptional:
    """Vars without hardcoded fallbacks must yield None when absent from the environment."""

    def test_opencode_server_dir_absent_is_none(self, monkeypatch):
        config = _reload_config(monkeypatch)
        assert config.OPENCODE_SERVER_DIR is None

    def test_github_token_absent_is_none(self, monkeypatch):
        config = _reload_config(monkeypatch)
        assert config.GITHUB_TOKEN is None

    def test_github_org_absent_is_none(self, monkeypatch):
        config = _reload_config(monkeypatch)
        assert config.GITHUB_ORG is None

    def test_github_repo_absent_is_none(self, monkeypatch):
        config = _reload_config(monkeypatch)
        assert config.GITHUB_REPO is None
