"""Temporal PayloadCodec for encrypting credential values in event history.

Encrypts JSON payloads that contain credential keys before Temporal stores
them, and decrypts on read so workers/workflows receive plaintext.
This prevents credential values from appearing in the Temporal UI or exports
while keeping the data functional for activity execution.

Layer 5 of 7-layer secret scrubbing.
"""

import json
import os
from collections.abc import Iterable

import structlog
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from temporalio.api.common.v1 import Payload
from temporalio.converter import PayloadCodec

from syntara.workflows.workflow_engine.utils.credential_scrubber import has_credential_keys

logger = structlog.stdlib.get_logger(__name__)

# Custom encoding marker for encrypted payloads
_ENCODING_ENCRYPTED = b"binary/encrypted"
_ENCODING_JSON = b"json/plain"
_NONCE_SIZE = 12


class CredentialPayloadCodec(PayloadCodec):
    """Encrypts payloads containing credential data before Temporal stores them.

    Only encrypts JSON payloads that contain recognized credential keys.
    Non-sensitive and non-JSON payloads pass through unchanged.
    Decryption restores the original plaintext for worker/workflow consumption.
    """

    def __init__(self, key: bytes) -> None:
        """Initialize with a 32-byte AES-256-GCM key.

        Args:
            key: 32-byte encryption key (same as APP_SECRET_ENCRYPTION_KEY).

        """
        self._aesgcm = AESGCM(key)

    async def encode(self, payloads: Iterable[Payload]) -> list[Payload]:
        """Encrypt payloads containing credential keys before Temporal stores them."""
        return [self._encrypt_if_sensitive(p) for p in payloads]

    async def decode(self, payloads: Iterable[Payload]) -> list[Payload]:
        """Decrypt previously encrypted payloads for worker/workflow consumption."""
        return [self._decrypt_if_encrypted(p) for p in payloads]

    def _encrypt_if_sensitive(self, payload: Payload) -> Payload:
        """Encrypt a payload if it contains credential keys."""
        encoding = payload.metadata.get("encoding", b"")
        if encoding != _ENCODING_JSON:
            return payload

        try:
            data = json.loads(payload.data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return payload

        if not has_credential_keys(data):
            return payload

        try:
            nonce = os.urandom(_NONCE_SIZE)
            ciphertext = self._aesgcm.encrypt(nonce, payload.data, None)
        except Exception as exc:
            logger.critical("Credential payload encryption failed — refusing to store plaintext", exc_info=True)
            msg = "Credential encryption failed; cannot store unencrypted secrets in Temporal"
            raise RuntimeError(msg) from exc

        result = Payload()
        result.metadata["encoding"] = _ENCODING_ENCRYPTED
        result.metadata["original_encoding"] = _ENCODING_JSON
        result.data = nonce + ciphertext
        return result

    def _decrypt_if_encrypted(self, payload: Payload) -> Payload:
        """Decrypt a payload if it was encrypted by encode()."""
        encoding = payload.metadata.get("encoding", b"")
        if encoding != _ENCODING_ENCRYPTED:
            return payload

        try:
            nonce = payload.data[:_NONCE_SIZE]
            ciphertext = payload.data[_NONCE_SIZE:]
            plaintext = self._aesgcm.decrypt(nonce, ciphertext, None)
        except Exception as exc:
            logger.critical("Credential payload decryption failed — cannot deliver corrupted data", exc_info=True)
            msg = "Credential decryption failed; activity cannot proceed with corrupted data"
            raise RuntimeError(msg) from exc

        result = Payload()
        original_encoding = payload.metadata.get("original_encoding", _ENCODING_JSON)
        result.metadata["encoding"] = original_encoding
        result.data = plaintext
        return result
