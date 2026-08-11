"""Tests for Temporal PayloadCodec credential encryption (T089)."""

import json
import os
from typing import Any

import pytest
from temporalio.api.common.v1 import Payload

from syntara.workflows.workflow_engine.codecs.credential_codec import CredentialPayloadCodec

# 32-byte test key for AES-256-GCM
_TEST_KEY = os.urandom(32)


def _make_json_payload(data: dict[str, Any]) -> Payload:
    """Create a Temporal Payload with JSON encoding."""
    payload = Payload()
    payload.metadata["encoding"] = b"json/plain"
    payload.data = json.dumps(data).encode("utf-8")
    return payload


def _make_binary_payload(data: bytes) -> Payload:
    """Create a Temporal Payload with binary encoding."""
    payload = Payload()
    payload.metadata["encoding"] = b"binary/plain"
    payload.data = data
    return payload


class TestCredentialPayloadCodec:
    """Tests for CredentialPayloadCodec encrypt/decrypt."""

    @pytest.mark.asyncio
    async def test_encode_encrypts_payload_with_credential_keys(self) -> None:
        codec = CredentialPayloadCodec(_TEST_KEY)
        payload = _make_json_payload(
            {
                "activity_id": "node-1",
                "bearer_token": "secret-token-123",
                "normal_field": "keep-this",
            }
        )

        result = await codec.encode([payload])

        # Encoded payload should be encrypted (not readable as JSON)
        assert result[0].metadata["encoding"] == b"binary/encrypted"
        with pytest.raises((json.JSONDecodeError, UnicodeDecodeError)):
            json.loads(result[0].data)

    @pytest.mark.asyncio
    async def test_roundtrip_preserves_data(self) -> None:
        codec = CredentialPayloadCodec(_TEST_KEY)
        original_data = {
            "activity_id": "node-1",
            "bearer_token": "secret-token-123",
            "api_key": "sk-abc",
            "normal_field": "keep-this",
        }
        payload = _make_json_payload(original_data)

        encoded = await codec.encode([payload])
        decoded = await codec.decode(encoded)

        result = json.loads(decoded[0].data)
        assert result == original_data

    @pytest.mark.asyncio
    async def test_roundtrip_nested_credential_keys(self) -> None:
        codec = CredentialPayloadCodec(_TEST_KEY)
        original_data = {
            "result": {
                "extra_vars": {
                    "bearer_token": "nested-secret",
                    "auth_type": "bearer",
                },
            },
        }
        payload = _make_json_payload(original_data)

        encoded = await codec.encode([payload])
        decoded = await codec.decode(encoded)

        result = json.loads(decoded[0].data)
        assert result == original_data

    @pytest.mark.asyncio
    async def test_encode_passes_non_credential_payloads_unchanged(self) -> None:
        codec = CredentialPayloadCodec(_TEST_KEY)
        data = {"workflow_id": "abc", "status": "completed", "count": 42}
        payload = _make_json_payload(data)

        result = await codec.encode([payload])

        # Non-sensitive payloads stay as json/plain
        assert result[0].metadata["encoding"] == b"json/plain"
        decoded = json.loads(result[0].data)
        assert decoded == data

    @pytest.mark.asyncio
    async def test_encode_passes_binary_payloads_unchanged(self) -> None:
        codec = CredentialPayloadCodec(_TEST_KEY)
        raw = b"\x00\x01\x02\x03"
        payload = _make_binary_payload(raw)

        result = await codec.encode([payload])

        assert result[0].data == raw

    @pytest.mark.asyncio
    async def test_decode_passes_non_encrypted_payloads_unchanged(self) -> None:
        codec = CredentialPayloadCodec(_TEST_KEY)
        payload = _make_json_payload({"bearer_token": "should-stay"})

        result = await codec.decode([payload])

        decoded = json.loads(result[0].data)
        assert decoded["bearer_token"] == "should-stay"  # noqa: S105

    @pytest.mark.asyncio
    async def test_roundtrip_list_with_credential_keys(self) -> None:
        codec = CredentialPayloadCodec(_TEST_KEY)
        original_data = {
            "items": [
                {"llm_api_key": "key-1", "name": "item-1"},
                {"name": "item-2"},
            ],
        }
        payload = _make_json_payload(original_data)

        encoded = await codec.encode([payload])
        decoded = await codec.decode(encoded)

        result = json.loads(decoded[0].data)
        assert result == original_data

    @pytest.mark.asyncio
    async def test_roundtrip_resolved_credentials_key(self) -> None:
        codec = CredentialPayloadCodec(_TEST_KEY)
        original_data = {
            "_resolved_credentials": {"credential_id": "abc", "extra_vars": {"token": "val"}},
            "other": "data",
        }
        payload = _make_json_payload(original_data)

        encoded = await codec.encode([payload])
        decoded = await codec.decode(encoded)

        result = json.loads(decoded[0].data)
        assert result == original_data

    @pytest.mark.asyncio
    async def test_encode_multiple_payloads(self) -> None:
        codec = CredentialPayloadCodec(_TEST_KEY)
        p1 = _make_json_payload({"bearer_token": "secret1"})
        p2 = _make_json_payload({"normal": "data"})
        p3 = _make_json_payload({"aap_password": "secret2"})

        result = await codec.encode([p1, p2, p3])

        assert len(result) == 3
        # p1 and p3 should be encrypted, p2 should be unchanged
        assert result[0].metadata["encoding"] == b"binary/encrypted"
        assert result[1].metadata["encoding"] == b"json/plain"
        assert result[2].metadata["encoding"] == b"binary/encrypted"

    @pytest.mark.asyncio
    async def test_different_encryptions_produce_different_ciphertext(self) -> None:
        codec = CredentialPayloadCodec(_TEST_KEY)
        payload1 = _make_json_payload({"bearer_token": "same-secret"})
        payload2 = _make_json_payload({"bearer_token": "same-secret"})

        result1 = await codec.encode([payload1])
        result2 = await codec.encode([payload2])

        # Different nonces should produce different ciphertext
        assert result1[0].data != result2[0].data
