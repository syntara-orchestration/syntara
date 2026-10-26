"""Authenticate terminal proofs independently of Redis namespace integrity."""

import hashlib
import hmac
import json
from functools import lru_cache

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from syntara.core.config.base import get_encryption_key
from syntara.eventstreams.core.terminal_proof import AuthenticatedTerminalProof, TerminalProof


@lru_cache(maxsize=1)
def _derive_signing_key() -> bytes:
    """Reuse the application secret with a purpose distinct from settings Pub/Sub.

    The key stays process-local and never enters Redis. Application-secret
    rotation makes old proofs misses; all service writers must share the key.
    """
    secret = get_encryption_key().get_secret_value()
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"eventstreams-terminal-proof-hmac:v1").derive(
        secret.encode()
    )


def _compute_mac(proof: TerminalProof) -> str:
    payload = json.dumps(proof.model_dump(mode="json", exclude={"mac"}), sort_keys=True, separators=(",", ":"))
    return hmac.new(_derive_signing_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def sign_terminal_proof(proof: TerminalProof) -> AuthenticatedTerminalProof:
    """Sign complete committed evidence; callers retain the commit boundary."""
    return AuthenticatedTerminalProof.model_validate({**proof.model_dump(), "mac": _compute_mac(proof)})


def verify_terminal_proof(proof: AuthenticatedTerminalProof) -> bool:
    """Authenticate every field before allowing it to replace a database read."""
    return hmac.compare_digest(_compute_mac(proof), proof.mac)
