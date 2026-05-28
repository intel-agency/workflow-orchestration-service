"""workflow-orchestration-client — Sentinel and webhook handler package."""

from importlib.metadata import version as _pkg_version, PackageNotFoundError as _PkgNotFoundError

try:
    __version__ = _pkg_version("workflow-orchestration-client")
except _PkgNotFoundError:  # pragma: no cover — editable install should always resolve
    __version__ = "0.0.0"