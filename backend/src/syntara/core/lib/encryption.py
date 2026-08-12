"""AES-256-GCM secret field encryption.

Provides authenticated encryption with per-field nonce and AAD binding
to prevent ciphertext substitution attacks between secrets.
"""

import base64
import binascii
import json
import os
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ENCRYPTED_SENTINEL = "$encrypted$"
NONCE_SIZE = 12  # 96-bit nonce for AES-GCM
KEY_SIZE = 32  # 256-bit key


class EncryptionError(Exception):
    """Raised when encryption or decryption fails."""


def key_from_string(hex_key: str, *, allow_insecure: bool = False) -> bytes:
    """Load an AES-256 key from a 64-character hex string.

    Args:
        hex_key: 64-character hex string representing 32 bytes.
        allow_insecure: Accept the all-zeros key (for key rotation from legacy defaults).

    Returns:
        32-byte key suitable for AES-256-GCM.

    Raises:
        ValueError: If the key is not a valid 64-character hex string.

    """
    key_bytes = bytes.fromhex(hex_key)
    if len(key_bytes) != KEY_SIZE:
        msg = f"Encryption key must be {KEY_SIZE} bytes ({KEY_SIZE * 2} hex chars), got {len(key_bytes)}"
        raise ValueError(msg)
    if not allow_insecure and key_bytes == b"\x00" * KEY_SIZE:
        msg = "Refusing to use the insecure all-zeros encryption key"
        raise ValueError(msg)
    return key_bytes


class SecretEncryptor:
    """Encrypts and decrypts secret field values using AES-256-GCM.

    Each field is encrypted with a unique random nonce and bound to the
    secret ID and field name via Associated Authenticated Data (AAD).
    This prevents swapping encrypted values between secrets or fields.

    Storage format: base64(nonce_12_bytes + ciphertext + tag_16_bytes)
    """

    def __init__(self, key: bytes) -> None:
        """Initialize with a 32-byte AES-256 key."""
        if len(key) != KEY_SIZE:
            msg = f"Key must be {KEY_SIZE} bytes, got {len(key)}"
            raise ValueError(msg)
        self._aesgcm = AESGCM(key)

    @staticmethod
    def _serialize_value(value: Any) -> str:  # noqa: ANN401
        """Serialize a field value to a string for encryption.

        All values are JSON-serialized to preserve type information
        during round-trip encryption/decryption.
        """
        return json.dumps(value)

    @staticmethod
    def _deserialize_value(serialized: str) -> Any:  # noqa: ANN401
        """Deserialize a field value from its string representation."""
        return json.loads(serialized)

    def _build_aad(self, secret_id: str, field_name: str) -> bytes:
        """Build AAD binding string: 'secret_id:field_name'."""
        return f"{secret_id}:{field_name}".encode()

    def encrypt_field(self, value: Any, secret_id: str, field_name: str) -> str:  # noqa: ANN401
        """Encrypt a single field value.

        Args:
            value: The field value (string, bool, int, etc.).
            secret_id: UUID of the secret (for AAD binding).
            field_name: Field identifier (for AAD binding).

        Returns:
            Base64-encoded string: nonce + ciphertext + tag.

        Raises:
            EncryptionError: If serialization or encryption fails.

        """
        try:
            serialized = self._serialize_value(value)
            nonce = os.urandom(NONCE_SIZE)
            aad = self._build_aad(secret_id, field_name)
            ciphertext = self._aesgcm.encrypt(nonce, serialized.encode("utf-8"), aad)
        except (TypeError, ValueError, OSError) as e:
            msg = f"Failed to encrypt field '{field_name}' for secret '{secret_id}'"
            raise EncryptionError(msg) from e
        return base64.b64encode(nonce + ciphertext).decode("ascii")

    def decrypt_field(self, encrypted_value: str, secret_id: str, field_name: str) -> Any:  # noqa: ANN401
        """Decrypt a single field value.

        Args:
            encrypted_value: Base64-encoded nonce + ciphertext + tag.
            secret_id: UUID of the secret (for AAD verification).
            field_name: Field identifier (for AAD verification).

        Returns:
            The original field value with its original type.

        Raises:
            EncryptionError: If decryption, decoding, or deserialization fails.

        """
        try:
            raw = base64.b64decode(encrypted_value)
        except binascii.Error as e:
            msg = f"Invalid base64 encoding for field '{field_name}' in secret '{secret_id}'"
            raise EncryptionError(msg) from e

        if len(raw) < NONCE_SIZE + 16:  # nonce (12) + GCM tag (16); empty plaintext = 28 bytes min
            msg = f"Encrypted value for field '{field_name}' in secret '{secret_id}' is too short"
            raise EncryptionError(msg)

        nonce = raw[:NONCE_SIZE]
        ciphertext = raw[NONCE_SIZE:]
        aad = self._build_aad(secret_id, field_name)

        try:
            plaintext = self._aesgcm.decrypt(nonce, ciphertext, aad)
        except InvalidTag as e:
            msg = (
                f"Decryption failed for field '{field_name}' in secret '{secret_id}'"
                " — wrong key, tampered data, or AAD mismatch"
            )
            raise EncryptionError(msg) from e

        try:
            return self._deserialize_value(plaintext.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            msg = f"Decrypted value for field '{field_name}' in secret '{secret_id}' is corrupted"
            raise EncryptionError(msg) from e

    def encrypt_fields(self, fields: dict[str, Any], secret_id: str) -> dict[str, str]:
        """Encrypt all field values in a dict.

        Args:
            fields: Dictionary of field_name -> plaintext value.
            secret_id: UUID of the secret.

        Returns:
            Dictionary of field_name -> encrypted base64 string.

        """
        return {name: self.encrypt_field(value, secret_id, name) for name, value in fields.items()}

    def decrypt_fields(self, encrypted_fields: dict[str, str], secret_id: str) -> dict[str, Any]:
        """Decrypt all field values in a dict.

        Args:
            encrypted_fields: Dictionary of field_name -> encrypted base64 string.
            secret_id: UUID of the secret.

        Returns:
            Dictionary of field_name -> plaintext value with original types.

        """
        return {name: self.decrypt_field(value, secret_id, name) for name, value in encrypted_fields.items()}
