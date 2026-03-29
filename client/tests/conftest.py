"""Pytest configuration and fixtures for OS-APOW tests.

This module provides shared fixtures and configuration for the test suite.
"""

import json
from pathlib import Path
from typing import Any

import pytest


# Fixture directories
FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the test fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def sample_issue_opened_payload() -> dict[str, Any]:
    """Return a sample issue opened webhook payload.

    Returns:
        Dictionary containing a sample GitHub issue opened event payload
    """
    return {
        "action": "opened",
        "issue": {
            "id": 123456789,
            "node_id": "MDU6SXNzdWUxMjM0NTY3ODk=",
            "number": 42,
            "title": "Test Issue for OS-APOW",
            "body": "This is a test issue for webhook testing.",
            "state": "open",
            "user": {
                "login": "testuser",
                "id": 987654,
                "node_id": "MDQ6VXNlcjk4NzY1NA==",
                "avatar_url": "https://github.com/images/error/testuser.gif",
                "html_url": "https://github.com/testuser",
                "type": "User",
            },
            "labels": [],
            "assignees": [],
            "milestone": None,
            "created_at": "2024-01-15T10:30:00Z",
            "updated_at": "2024-01-15T10:30:00Z",
            "html_url": "https://github.com/testowner/testrepo/issues/42",
        },
        "repository": {
            "id": 111222333,
            "node_id": "MDEwOlJlcG9zaXRvcnkxMTEyMjIzMzM=",
            "name": "testrepo",
            "full_name": "testowner/testrepo",
            "private": False,
            "owner": {
                "login": "testowner",
                "id": 555666,
                "node_id": "MDQ6VXNlcjU1NTY2Ng==",
                "avatar_url": "https://github.com/images/error/testowner.gif",
                "html_url": "https://github.com/testowner",
                "type": "User",
            },
            "html_url": "https://github.com/testowner/testrepo",
            "default_branch": "main",
        },
        "sender": {
            "login": "testuser",
            "id": 987654,
            "node_id": "MDQ6VXNlcjk4NzY1NA==",
            "avatar_url": "https://github.com/images/error/testuser.gif",
            "html_url": "https://github.com/testuser",
            "type": "User",
        },
    }


@pytest.fixture
def sample_issue_labeled_payload() -> dict[str, Any]:
    """Return a sample issue labeled webhook payload.

    Returns:
        Dictionary containing a sample GitHub issue labeled event payload
    """
    return {
        "action": "labeled",
        "issue": {
            "id": 123456789,
            "node_id": "MDU6SXNzdWUxMjM0NTY3ODk=",
            "number": 42,
            "title": "Test Issue for OS-APOW",
            "body": "This is a test issue for webhook testing.",
            "state": "open",
            "user": {
                "login": "testuser",
                "id": 987654,
                "node_id": "MDQ6VXNlcjk4NzY1NA==",
                "avatar_url": "https://github.com/images/error/testuser.gif",
                "html_url": "https://github.com/testuser",
                "type": "User",
            },
            "labels": [
                {
                    "id": 111222,
                    "node_id": "MDU6TGFiZWwxMTEyMjI=",
                    "name": "orchestrator:dispatch",
                    "description": "Trigger orchestrator dispatch",
                    "color": "0e8a16",
                    "default": False,
                }
            ],
            "assignees": [],
            "milestone": None,
            "created_at": "2024-01-15T10:30:00Z",
            "updated_at": "2024-01-15T10:35:00Z",
            "html_url": "https://github.com/testowner/testrepo/issues/42",
        },
        "label": {
            "id": 111222,
            "node_id": "MDU6TGFiZWwxMTEyMjI=",
            "name": "orchestrator:dispatch",
            "description": "Trigger orchestrator dispatch",
            "color": "0e8a16",
            "default": False,
        },
        "repository": {
            "id": 111222333,
            "node_id": "MDEwOlJlcG9zaXRvcnkxMTEyMjIzMzM=",
            "name": "testrepo",
            "full_name": "testowner/testrepo",
            "private": False,
            "owner": {
                "login": "testowner",
                "id": 555666,
                "node_id": "MDQ6VXNlcjU1NTY2Ng==",
                "avatar_url": "https://github.com/images/error/testowner.gif",
                "html_url": "https://github.com/testowner",
                "type": "User",
            },
            "html_url": "https://github.com/testowner/testrepo",
            "default_branch": "main",
        },
        "sender": {
            "login": "testuser",
            "id": 987654,
            "node_id": "MDQ6VXNlcjk4NzY1NA==",
            "avatar_url": "https://github.com/images/error/testuser.gif",
            "html_url": "https://github.com/testuser",
            "type": "User",
        },
    }


@pytest.fixture
def sample_pr_opened_payload() -> dict[str, Any]:
    """Return a sample pull request opened webhook payload.

    Returns:
        Dictionary containing a sample GitHub PR opened event payload
    """
    return {
        "action": "opened",
        "number": 15,
        "pull_request": {
            "id": 987654321,
            "node_id": "MDExOlB1bGxSZXF1ZXN0OTg3NjU0MzIx",
            "number": 15,
            "title": "Test PR for OS-APOW",
            "body": "This is a test pull request for webhook testing.",
            "state": "open",
            "draft": False,
            "merged": False,
            "user": {
                "login": "testuser",
                "id": 987654,
                "node_id": "MDQ6VXNlcjk4NzY1NA==",
                "avatar_url": "https://github.com/images/error/testuser.gif",
                "html_url": "https://github.com/testuser",
                "type": "User",
            },
            "labels": [],
            "assignees": [],
            "requested_reviewers": [],
            "milestone": None,
            "created_at": "2024-01-15T11:00:00Z",
            "updated_at": "2024-01-15T11:00:00Z",
            "html_url": "https://github.com/testowner/testrepo/pull/15",
        },
        "repository": {
            "id": 111222333,
            "node_id": "MDEwOlJlcG9zaXRvcnkxMTEyMjIzMzM=",
            "name": "testrepo",
            "full_name": "testowner/testrepo",
            "private": False,
            "owner": {
                "login": "testowner",
                "id": 555666,
                "node_id": "MDQ6VXNlcjU1NTY2Ng==",
                "avatar_url": "https://github.com/images/error/testowner.gif",
                "html_url": "https://github.com/testowner",
                "type": "User",
            },
            "html_url": "https://github.com/testowner/testrepo",
            "default_branch": "main",
        },
        "sender": {
            "login": "testuser",
            "id": 987654,
            "node_id": "MDQ6VXNlcjk4NzY1NA==",
            "avatar_url": "https://github.com/images/error/testuser.gif",
            "html_url": "https://github.com/testuser",
            "type": "User",
        },
    }


@pytest.fixture
def sample_work_item_dict() -> dict[str, Any]:
    """Return a sample work item dictionary.

    Returns:
        Dictionary containing a sample work item for testing
    """
    return {
        "id": "issue-42-labeled",
        "event_type": "issues",
        "action": "labeled",
        "payload": {
            "action": "labeled",
            "issue": {
                "number": 42,
                "title": "Test Issue",
            },
        },
        "status": "pending",
        "priority": 5,
    }


@pytest.fixture
def webhook_headers() -> dict[str, str]:
    """Return sample webhook headers.

    Returns:
        Dictionary containing sample GitHub webhook headers
    """
    return {
        "X-GitHub-Event": "issues",
        "X-GitHub-Delivery": "12345678-1234-1234-1234-123456789012",
        "X-Hub-Signature-256": "sha256=abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        "Content-Type": "application/json",
    }


@pytest.fixture
def test_settings() -> dict[str, Any]:
    """Return test configuration settings.

    Returns:
        Dictionary containing test environment settings
    """
    return {
        "app_name": "OS-APOW Test",
        "app_version": "0.1.0-test",
        "debug": True,
        "webhook_secret": "test-secret-for-testing-only",
        "hmac_algorithm": "sha256",
        "host": "127.0.0.1",
        "port": 8001,
    }


def load_fixture(fixture_name: str) -> dict[str, Any]:
    """Load a JSON fixture file.

    Args:
        fixture_name: Name of the fixture file (without .json extension)

    Returns:
        Parsed JSON content as a dictionary

    Raises:
        FileNotFoundError: If the fixture file doesn't exist
        json.JSONDecodeError: If the fixture contains invalid JSON
    """
    fixture_path = FIXTURES_DIR / f"{fixture_name}.json"
    if not fixture_path.exists():
        raise FileNotFoundError(f"Fixture not found: {fixture_path}")

    with fixture_path.open("r") as f:
        return json.load(f)
