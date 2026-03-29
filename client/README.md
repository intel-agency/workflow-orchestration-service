# OS-APOW Client

Orchestration Service - Autonomous Pipeline for Orchestrated Workflows

## Overview

This package provides the Python client components for the standalone orchestration
service migration. It includes:

- **Webhook Notifier Service**: FastAPI-based webhook receiver with HMAC verification
- **Orchestrator Sentinel**: Shell-bridge dispatcher integration
- **Work Queue Models**: Pydantic models for work items and event payloads

## Requirements

- Python 3.12+
- uv package manager

## Installation

```bash
cd client
uv sync
```

## Development

```bash
# Install dev dependencies
uv sync --group dev

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov

# Type checking
uv run mypy src

# Linting
uv run ruff check src
```

## Project Structure

```
client/
├── src/
│   ├── __init__.py
│   ├── notifier_service.py    # FastAPI webhook receiver
│   ├── orchestrator_sentinel.py  # Shell-bridge dispatcher
│   └── models/                # Pydantic models
│       ├── __init__.py
│       ├── work_item.py
│       └── schemas.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   └── fixtures/
├── pyproject.toml
└── README.md
```

## License

MIT
