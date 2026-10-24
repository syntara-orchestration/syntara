"""Public workflow authentication facade."""

from syntara.workflow_runtime.engines.temporal.workflow_auth import build_auth_header

__all__ = ["build_auth_header"]
