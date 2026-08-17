"""Tests for SecretEncryptor — AES-256-GCM field encryption."""

import base64
import os

import pytest

from syntara.core.lib.encryption import (
    ENCRYPTED_SENTINEL,
    KEY_SIZE,
    EncryptionError,
    SecretEncryptor,
    key_from_string,
)

VALID_HEX_KEY = os.urandom(KEY_SIZE).hex()
SECRET_ID = "550e8400-e29b-41d4-a716-446655440000"  # noqa: S105


@pytest.fixture
def encryptor() -> SecretEncryptor:
    """Create an encryptor with a random key."""
    return SecretEncryptor(bytes.fromhex(VALID_HEX_KEY))


class TestKeyFromString:
    """Tests for hex key loading."""

    def test_valid_hex_key(self) -> None:
        key = key_from_string(VALID_HEX_KEY)
        assert len(key) == KEY_SIZE

    def test_invalid_hex_chars(self) -> None:
        with pytest.raises(ValueError, match="non-hexadecimal"):
            key_from_string("z" * 64)

    def test_wrong_length(self) -> None:
        with pytest.raises(ValueError, match="32 bytes"):
            key_from_string("abcd1234")


class TestEncryptDecryptRoundTrip:
    """Verify that encrypt then decrypt returns the original value."""

    def test_string_round_trip(self, encryptor: SecretEncryptor) -> None:
        original = "sk-abc-123-secret-token"
        encrypted = encryptor.encrypt_field(original, SECRET_ID, "token")
        decrypted = encryptor.decrypt_field(encrypted, SECRET_ID, "token")
        assert decrypted == original

    def test_boolean_true_round_trip(self, encryptor: SecretEncryptor) -> None:
        encrypted = encryptor.encrypt_field(True, SECRET_ID, "verify_ssl")  # noqa: FBT003
        decrypted = encryptor.decrypt_field(encrypted, SECRET_ID, "verify_ssl")
        assert decrypted is True

    def test_boolean_false_round_trip(self, encryptor: SecretEncryptor) -> None:
        encrypted = encryptor.encrypt_field(False, SECRET_ID, "verify_ssl")  # noqa: FBT003
        decrypted = encryptor.decrypt_field(encrypted, SECRET_ID, "verify_ssl")
        assert decrypted is False

    def test_integer_round_trip(self, encryptor: SecretEncryptor) -> None:
        encrypted = encryptor.encrypt_field(8080, SECRET_ID, "port")
        decrypted = encryptor.decrypt_field(encrypted, SECRET_ID, "port")
        assert decrypted == 8080

    def test_none_round_trip(self, encryptor: SecretEncryptor) -> None:
        encrypted = encryptor.encrypt_field(None, SECRET_ID, "optional_field")
        decrypted = encryptor.decrypt_field(encrypted, SECRET_ID, "optional_field")
        assert decrypted is None

    def test_empty_string_round_trip(self, encryptor: SecretEncryptor) -> None:
        encrypted = encryptor.encrypt_field("", SECRET_ID, "empty")
        decrypted = encryptor.decrypt_field(encrypted, SECRET_ID, "empty")
        assert decrypted == ""


class TestNonceUniqueness:
    """Verify that each encryption produces a unique ciphertext."""

    def test_same_value_different_ciphertext(self, encryptor: SecretEncryptor) -> None:
        value = "same-secret"
        enc1 = encryptor.encrypt_field(value, SECRET_ID, "token")
        enc2 = encryptor.encrypt_field(value, SECRET_ID, "token")
        assert enc1 != enc2

    def test_both_decrypt_correctly(self, encryptor: SecretEncryptor) -> None:
        value = "same-secret"
        enc1 = encryptor.encrypt_field(value, SECRET_ID, "token")
        enc2 = encryptor.encrypt_field(value, SECRET_ID, "token")
        assert encryptor.decrypt_field(enc1, SECRET_ID, "token") == value
        assert encryptor.decrypt_field(enc2, SECRET_ID, "token") == value


class TestAADBinding:
    """Verify that AAD prevents ciphertext substitution attacks."""

    def test_wrong_credential_id_rejected(self, encryptor: SecretEncryptor) -> None:
        encrypted = encryptor.encrypt_field("secret", SECRET_ID, "token")
        wrong_id = "00000000-0000-0000-0000-000000000000"
        with pytest.raises(EncryptionError, match="Decryption failed"):
            encryptor.decrypt_field(encrypted, wrong_id, "token")

    def test_wrong_field_name_rejected(self, encryptor: SecretEncryptor) -> None:
        encrypted = encryptor.encrypt_field("secret", SECRET_ID, "token")
        with pytest.raises(EncryptionError, match="Decryption failed"):
            encryptor.decrypt_field(encrypted, SECRET_ID, "password")

    def test_swapped_fields_rejected(self, encryptor: SecretEncryptor) -> None:
        enc_token = encryptor.encrypt_field("token-val", SECRET_ID, "token")
        enc_pass = encryptor.encrypt_field("pass-val", SECRET_ID, "password")
        with pytest.raises(EncryptionError, match="Decryption failed"):
            encryptor.decrypt_field(enc_token, SECRET_ID, "password")
        with pytest.raises(EncryptionError, match="Decryption failed"):
            encryptor.decrypt_field(enc_pass, SECRET_ID, "token")


class TestInvalidKeyHandling:
    """Verify key validation."""

    def test_wrong_key_size(self) -> None:
        with pytest.raises(ValueError, match="32 bytes"):
            SecretEncryptor(b"too-short")

    def test_empty_key(self) -> None:
        with pytest.raises(ValueError, match="32 bytes"):
            SecretEncryptor(b"")

    def test_wrong_key_cannot_decrypt(self) -> None:
        key1 = os.urandom(KEY_SIZE)
        key2 = os.urandom(KEY_SIZE)
        enc1 = SecretEncryptor(key1)
        enc2 = SecretEncryptor(key2)
        encrypted = enc1.encrypt_field("secret", SECRET_ID, "token")
        with pytest.raises(EncryptionError, match="Decryption failed"):
            enc2.decrypt_field(encrypted, SECRET_ID, "token")


class TestErrorHandling:
    """Verify proper error handling for invalid inputs."""

    def test_invalid_base64_rejected(self, encryptor: SecretEncryptor) -> None:
        with pytest.raises(EncryptionError, match="Invalid base64"):
            encryptor.decrypt_field("not-valid-base64!!!", SECRET_ID, "token")

    def test_ciphertext_too_short_rejected(self, encryptor: SecretEncryptor) -> None:
        short = base64.b64encode(os.urandom(20)).decode("ascii")
        with pytest.raises(EncryptionError, match="too short"):
            encryptor.decrypt_field(short, SECRET_ID, "token")

    def test_tampered_ciphertext_rejected(self, encryptor: SecretEncryptor) -> None:
        encrypted = encryptor.encrypt_field("secret", SECRET_ID, "token")
        raw = bytearray(base64.b64decode(encrypted))
        raw[20] ^= 0xFF  # flip a byte in the ciphertext
        tampered = base64.b64encode(bytes(raw)).decode("ascii")
        with pytest.raises(EncryptionError, match="Decryption failed"):
            encryptor.decrypt_field(tampered, SECRET_ID, "token")


class TestEncryptDecryptFields:
    """Tests for bulk field encryption and decryption."""

    def test_encrypt_decrypt_all_fields(self, encryptor: SecretEncryptor) -> None:
        fields = {
            "token": "sk-abc-123",
            "host": "api.example.com",
            "verify_ssl": True,
            "port": 443,
        }
        encrypted = encryptor.encrypt_fields(fields, SECRET_ID)
        assert set(encrypted.keys()) == set(fields.keys())
        for name, value in encrypted.items():
            assert value != str(fields[name])

        decrypted = encryptor.decrypt_fields(encrypted, SECRET_ID)
        assert decrypted == fields

    def test_empty_fields(self, encryptor: SecretEncryptor) -> None:
        encrypted = encryptor.encrypt_fields({}, SECRET_ID)
        assert encrypted == {}
        decrypted = encryptor.decrypt_fields({}, SECRET_ID)
        assert decrypted == {}


class TestEncryptedSentinel:
    """Verify the sentinel constant is available."""

    def test_sentinel_value(self) -> None:
        assert ENCRYPTED_SENTINEL == "$encrypted$"
