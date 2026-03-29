"""FastAPI webhook notifier service for OS-APOW.

This module provides the webhook receiver endpoint that accepts notifications
from the orchestration system and processes them through the work queue.
"""

import hashlib
import hmac
import logging
from typing import Annotated, Any

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel
from pydantic_settings import BaseSettings
import structlog

# Configure structured logging
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
)

logger = structlog.get_logger()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_name: str = "OS-APOW Webhook Notifier"
    app_version: str = "0.1.0"
    debug: bool = False

    # HMAC signature verification
    webhook_secret: str = ""
    hmac_algorithm: str = "sha256"
    hmac_header_name: str = "X-Signature-256"

    # Server configuration
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = {"env_prefix": "OS_APOW_", "env_file": ".env"}


settings = Settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Webhook notifier service for the Orchestration Service",
)


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    version: str
    service: str


class WebhookPayload(BaseModel):
    """Incoming webhook payload model.

    This is a placeholder schema that will be replaced with
    proper event payload models from the models module.
    """

    event_type: str
    action: str | None = None
    data: dict[str, Any]
    timestamp: str | None = None


class WebhookResponse(BaseModel):
    """Webhook processing response."""

    status: str
    message: str
    event_id: str | None = None


def verify_hmac_signature(
    payload: bytes,
    signature: str,
    secret: str,
    algorithm: str = "sha256",
) -> bool:
    """Verify HMAC signature of the payload.

    Args:
        payload: Raw request body bytes
        signature: Signature from header (format: "sha256=...")
        secret: Shared secret for HMAC
        algorithm: Hash algorithm to use

    Returns:
        True if signature is valid, False otherwise
    """
    if not secret:
        logger.warning("webhook_secret_not_configured")
        return True  # Skip verification if no secret configured

    if not signature:
        logger.warning("signature_header_missing")
        return False

    try:
        # Parse algorithm from signature (e.g., "sha256=abc123" -> "sha256")
        if "=" in signature:
            sig_algorithm, sig_value = signature.split("=", 1)
            if sig_algorithm.lower() != algorithm.lower():
                logger.warning(
                    "algorithm_mismatch",
                    expected=algorithm,
                    received=sig_algorithm,
                )
                return False
        else:
            sig_value = signature

        # Compute expected signature
        expected = hmac.new(
            secret.encode(),
            payload,
            getattr(hashlib, algorithm.lower()),
        ).hexdigest()

        # Use constant-time comparison to prevent timing attacks
        return hmac.compare_digest(expected, sig_value)
    except (AttributeError, ValueError) as e:
        logger.error("signature_verification_error", error=str(e))
        return False


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint.

    Returns basic service information for monitoring and load balancer checks.
    """
    return HealthResponse(
        status="healthy",
        version=settings.app_version,
        service=settings.app_name,
    )


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint with service information."""
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
    }


@app.post("/webhook", response_model=WebhookResponse)
async def receive_webhook(
    request: Request,
    payload: WebhookPayload,
    x_signature_256: Annotated[str | None, Header()] = None,
) -> WebhookResponse:
    """Receive and process webhook notifications.

    This endpoint accepts webhook payloads from the orchestration system.
    HMAC signature verification is performed when a webhook secret is configured.

    Args:
        request: FastAPI request object for accessing raw body
        payload: Parsed webhook payload
        x_signature_256: HMAC signature header (optional)

    Returns:
        WebhookResponse indicating processing status

    Raises:
        HTTPException: If signature verification fails or payload is invalid
    """
    logger.info(
        "webhook_received",
        event_type=payload.event_type,
        action=payload.action,
    )

    # Verify HMAC signature
    raw_body = await request.body()
    signature = x_signature_256 or ""

    if not verify_hmac_signature(
        raw_body,
        signature,
        settings.webhook_secret,
        settings.hmac_algorithm,
    ):
        logger.warning("webhook_signature_invalid")
        raise HTTPException(status_code=401, detail="Invalid signature")

    # TODO: Queue the work item for processing by orchestrator_sentinel
    # This will be implemented in the shell-bridge dispatcher integration
    logger.info(
        "webhook_queued",
        event_type=payload.event_type,
        data_keys=list(payload.data.keys()),
    )

    return WebhookResponse(
        status="accepted",
        message="Webhook received and queued for processing",
        event_id=f"{payload.event_type}-{payload.timestamp or 'pending'}",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "notifier_service:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
