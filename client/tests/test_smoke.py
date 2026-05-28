"""
Smoke tests — verify the workflow-orchestration-client package installs
and the top-level `src` package is importable. Full module-level tests
(config, notifier, sentinel, work_item, github_queue) ship in f5-f9.
"""


def test_imports():
    """Verify the src package is importable after editable install."""
    import src  # noqa: F401
