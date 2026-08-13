"""Workflow authorization via HMAC-signed Temporal headers.

Derives a purpose-specific signing key from APP_SECRET_ENCRYPTION_KEY
using HKDF (RFC 5869) and signs workflow submissions with HMAC-SHA256.
The MAC binds workflow_id, workflow_type, and a fingerprint of the
start arguments so that a captured token cannot be replayed with
different arguments or a different workflow type.

Pre-existing schedules: no migration path is provided — this is a
greenfield deployment.  All schedules are created with auth headers
from the publish path.  If deployed over an existing Temporal namespace,
pre-existing schedules must be republished to acquire headers.
"""

import hashlib
import hmac as hmac_mod
import json
from collections.abc import Sequence
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from temporalio.api.common.v1 import Payload

HEADER_NAME = "x-workflow-auth"

_signing_key: bytes | None = None


def init_signing_key() -> None:
    """Derive and cache the signing key from the application secret.

    Must be called at process startup (API server init, worker init)
    before any workflows run.  This avoids lazy imports inside the
    Temporal workflow sandbox, which blocks access to ``os.environ``.
    """
    global _signing_key  # noqa: PLW0603
    if _signing_key is None:
        from syntara.core.config.base import get_encryption_key  # noqa: PLC0415

        secret = get_encryption_key().get_secret_value()
        hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"temporal-workflow-auth")
        _signing_key = hkdf.derive(secret.encode())


def _get_signing_key() -> bytes:
    """Return the cached signing key, initializing lazily if needed.

    The lazy path is only hit outside the workflow sandbox (API process,
    schedule service).  Inside the sandbox, ``init_signing_key`` must
    have been called at worker startup.
    """
    if _signing_key is None:
        init_signing_key()
    return _signing_key  # type: ignore[return-value]


def _fingerprint_args(args: Sequence[Any]) -> str:
    """Deterministic SHA-256 hex digest of workflow start arguments."""
    canonical = json.dumps(list(args), sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def sign_workflow(workflow_id: str, workflow_type: str, args: Sequence[Any]) -> bytes:
    """Compute HMAC-SHA256 over workflow ID, type, and args fingerprint."""
    message = f"{workflow_id}\n{workflow_type}\n{_fingerprint_args(args)}".encode()
    return hmac_mod.new(_get_signing_key(), message, hashlib.sha256).digest()


def verify_workflow(workflow_id: str, workflow_type: str, args: Sequence[Any], token: bytes) -> bool:
    """Verify an HMAC-SHA256 token using constant-time comparison."""
    expected = sign_workflow(workflow_id, workflow_type, args)
    return hmac_mod.compare_digest(expected, token)


def build_auth_header(workflow_id: str, workflow_type: str, args: Sequence[Any]) -> dict[str, Payload]:
    """Build a Temporal header dict containing the signed workflow submission."""
    return {HEADER_NAME: Payload(data=sign_workflow(workflow_id, workflow_type, args))}
