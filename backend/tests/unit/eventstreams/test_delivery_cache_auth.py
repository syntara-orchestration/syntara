"""Terminal-proof authenticity under Redis write access, without live services."""

import hmac
from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from pydantic import SecretStr, ValidationError

from syntara.eventstreams.core.terminal_proof import AuthenticatedTerminalProof, TerminalProof
from syntara.eventstreams.services import delivery_cache_auth
from syntara.eventstreams.services.delivery_cache_auth import sign_terminal_proof, verify_terminal_proof
from tests.unit.eventstreams.test_terminal_proof import proof


@pytest.fixture(autouse=True)
def application_secret(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Exercise actual HKDF using an isolated test secret, never deployment keys."""
    delivery_cache_auth._derive_signing_key.cache_clear()
    monkeypatch.setattr(delivery_cache_auth, "get_encryption_key", lambda: SecretStr("test-application-secret"))
    yield
    delivery_cache_auth._derive_signing_key.cache_clear()


def test_signed_round_trip_and_constant_time_comparison(monkeypatch: pytest.MonkeyPatch) -> None:
    signed = sign_terminal_proof(proof())
    parsed = AuthenticatedTerminalProof.model_validate_json(signed.model_dump_json())
    compare = MagicMock(wraps=hmac.compare_digest)
    monkeypatch.setattr(hmac, "compare_digest", compare)
    assert verify_terminal_proof(parsed)
    compare.assert_called_once()
    assert parsed.terminal() == proof().terminal()


@pytest.mark.parametrize("field", list(TerminalProof.model_fields))
def test_mac_covers_every_proof_field(field: str) -> None:
    signed = sign_terminal_proof(proof())
    # Deliberately bypass type validation to isolate MAC coverage of each field.
    tampered = signed.model_copy(update={field: None if getattr(signed, field) is not None else "changed"})
    assert not verify_terminal_proof(tampered)


def test_wrong_application_key_cannot_verify_proof(monkeypatch: pytest.MonkeyPatch) -> None:
    signed = sign_terminal_proof(proof())
    delivery_cache_auth._derive_signing_key.cache_clear()
    monkeypatch.setattr(delivery_cache_auth, "get_encryption_key", lambda: SecretStr("different-test-secret"))
    assert not verify_terminal_proof(signed)


def test_hkdf_purpose_is_distinct_from_settings_pubsub() -> None:
    secret = b"test-application-secret"
    expected = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=b"eventstreams-terminal-proof-hmac:v1"
    ).derive(secret)
    settings_key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"settings-pubsub-hmac").derive(secret)
    assert delivery_cache_auth._derive_signing_key() == expected
    assert expected != settings_key


def test_unsigned_proof_is_not_an_authenticated_wire_value() -> None:
    with pytest.raises(ValidationError):
        AuthenticatedTerminalProof.model_validate_json(proof().model_dump_json())


def test_signed_entry_limit_includes_authentication_tag() -> None:
    signed = sign_terminal_proof(proof())
    size = len(signed.model_dump_json().encode())
    assert size <= 4096
    assert size > len(proof().model_dump_json().encode())
    # Keep the unsigned value just below the cap; its tag must also fit.
    digits_to_add = 4090 - len(proof().model_dump_json().encode())
    identity = proof().identity.model_copy(update={"source_generation": 10**digits_to_add})
    unsigned = TerminalProof.model_validate(
        {
            **proof().model_dump(),
            "identity": identity,
            "identity_digest": identity.digest,
            "execution_id": identity.execution_id,
            "temporal_workflow_id": identity.temporal_workflow_id,
        }
    )
    with pytest.raises(ValidationError, match="serialized entry limit"):
        sign_terminal_proof(unsigned)
