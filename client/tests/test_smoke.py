"""
Smoke tests — verify the workflow-orchestration-client package installs,
the top-level `src` package is importable, and version metadata is sane.
Full module-level tests (config, notifier, sentinel, work_item, github_queue)
ship in f5-f9.
"""

from importlib.metadata import version as pkg_version


def test_imports():
    """Verify the src package is importable after editable install."""
    import src  # noqa: F401


def test_version_attribute_exists():
    """The src package exposes a __version__ attribute."""
    import src

    assert hasattr(src, "__version__")
    assert isinstance(src.__version__, str)


def test_version_matches_pyproject():
    """__version__ in src matches the distribution metadata from pyproject.toml."""
    import src

    dist_version = pkg_version("workflow-orchestration-client")
    assert src.__version__ == dist_version
    # Sanity: version string looks like semver (major.minor.patch)
    parts = src.__version__.split(".")
    assert len(parts) >= 2, f"Version {src.__version__!r} should have at least major.minor"


def test_all_modules_importable():
    """Every rewritten module is importable from the installed package."""
    import src.config  # noqa: F401
    import src.notifier  # noqa: F401
    import src.sentinel  # noqa: F401
    import src.models.work_item  # noqa: F401
    import src.queue.github_queue  # noqa: F401
