"""Measure complete arguments including the worker's credential-codec envelope."""

from collections.abc import Sequence
from typing import Any

from temporalio.api.common.v1 import Payload, Payloads
from temporalio.converter import DataConverter

from syntara.workflows.workflow_engine.codecs.credential_codec import _ENCODING_ENCRYPTED, _NONCE_SIZE
from syntara.workflows.workflow_engine.utils.credential_scrubber import has_credential_keys

_AES_GCM_TAG_BYTES = 16


def temporal_argument_size(arguments: Sequence[Any]) -> int:
    """Count actual converter bytes and exact codec framing without random encryption.

    Ciphertext length is plaintext length plus the AES-GCM tag and nonce.
    Predicting bytes this way is deterministic in the workflow sandbox. Tests
    compare it with the actual worker codec; no plaintext is put into errors.
    """
    payloads = DataConverter.default.payload_converter.to_payloads(arguments)
    encoded: list[Payload] = []
    for payload in payloads:
        encoded_payload = payload
        if payload.metadata.get("encoding") == b"json/plain":
            values = DataConverter.default.payload_converter.from_payloads([payload])
            if has_credential_keys(values[0]):
                encoded_payload = Payload(
                    metadata={"encoding": _ENCODING_ENCRYPTED, "original_encoding": b"json/plain"},
                    data=bytes(len(payload.data) + _NONCE_SIZE + _AES_GCM_TAG_BYTES),
                )
        encoded.append(encoded_payload)
    return Payloads(payloads=encoded).ByteSize()
