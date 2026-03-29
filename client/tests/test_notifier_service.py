"""Tests for the webhook notifier service."""

import hashlib
import hmac
import pytest
from unittest.mock import AsyncMock, patch

# Note: These tests require the dependencies to be installed
# Run: uv sync --group dev


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_check_returns_healthy(self):
        """Test that health endpoint returns healthy status."""
        # TODO: Implement with FastAPI TestClient
        # This is a placeholder for the integration test
        pass

    @pytest.mark.asyncio
    async def test_health_check_includes_version(self):
        """Test that health endpoint includes version."""
        # TODO: Implement with FastAPI TestClient
        pass


class TestWebhookEndpoint:
    """Tests for the webhook receiver endpoint."""

    @pytest.mark.asyncio
    async def test_receive_webhook_without_signature(self, sample_issue_opened_payload):
        """Test receiving webhook without HMAC signature (when secret not configured)."""
        # TODO: Implement with FastAPI TestClient
        pass

    @pytest.mark.asyncio
    async def test_receive_webhook_with_valid_signature(
        self, sample_issue_labeled_payload, test_settings
    ):
        """Test receiving webhook with valid HMAC signature."""
        # TODO: Implement with FastAPI TestClient
        pass

    @pytest.mark.asyncio
    async def test_receive_webhook_with_invalid_signature(self, sample_issue_labeled_payload):
        """Test that invalid signature is rejected."""
        # TODO: Implement with FastAPI TestClient
        pass


class TestHMACVerification:
    """Tests for HMAC signature verification."""

    def test_verify_hmac_valid_signature(self, test_settings):
        """Test HMAC verification with valid signature."""
        # Import here to avoid import errors when deps not installed
        # from src.notifier_service import verify_hmac_signature

        secret = test_settings["webhook_secret"]
        payload = b'{"test": "data"}'

        # Compute expected signature
        expected_sig = hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        # TODO: Call verify_hmac_signature and assert True
        pass

    def test_verify_hmac_invalid_signature(self, test_settings):
        """Test HMAC verification with invalid signature."""
        # TODO: Implement
        pass

    def test_verify_hmac_empty_secret_allows_all(self):
        """Test that empty secret skips verification."""
        # TODO: Implement
        pass

    def test_verify_hmac_missing_header_rejects(self):
        """Test that missing signature header is rejected."""
        # TODO: Implement
        pass


class TestRootEndpoint:
    """Tests for the root endpoint."""

    @pytest.mark.asyncio
    async def test_root_returns_service_info(self):
        """Test that root endpoint returns service information."""
        # TODO: Implement with FastAPI TestClient
        pass
