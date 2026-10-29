"""Non-secret revision generation and compatibility contract."""

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from syntara.eventstreams.core.connection_revision import ConnectionRevision

NOW = datetime(2026, 10, 19, 12, 34, 56, 123456, tzinfo=UTC)


def revision() -> ConnectionRevision:
    """Construct identifiers without loading credential contents."""
    return ConnectionRevision(
        integration_id=UUID(int=1),
        integration_updated_at=NOW,
        credential_id=UUID(int=2),
        credential_updated_at=NOW,
        credential_type_id=UUID(int=3),
        credential_type_updated_at=NOW,
        secret_id=UUID(int=4),
        secret_updated_at=NOW,
    )


def test_revision_is_stable_versioned_and_bounded() -> None:
    value = revision()
    assert value.digest == ConnectionRevision.model_validate_json(value.model_dump_json()).digest
    assert value.digest.startswith("connection-v1:")
    assert len(value.digest) < 128
    assert value.model_dump(mode="json")["revision_version"] == 1


@pytest.mark.parametrize(
    "field", ["integration_updated_at", "credential_updated_at", "credential_type_updated_at", "secret_updated_at"]
)
def test_resource_changes_change_revision(field: str) -> None:
    value = revision()
    changed = value.model_copy(update={field: NOW + timedelta(microseconds=1)})
    assert changed.digest != value.digest
    same_instant = NOW.astimezone(timezone(timedelta(hours=5, minutes=30)))
    assert value.model_copy(update={field: same_instant}).digest == value.digest


@pytest.mark.parametrize("field", ["integration_id", "credential_id", "credential_type_id", "secret_id"])
def test_resource_replacement_changes_revision(field: str) -> None:
    assert revision().model_copy(update={field: UUID(int=99)}).digest != revision().digest


@pytest.mark.parametrize("field", ["password", "encrypted_data", "resolved_credential"])
def test_secret_contents_are_not_revision_inputs(field: str) -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        ConnectionRevision.model_validate({**revision().model_dump(), field: "PRIVATE"})


def test_revision_is_immutable_and_rejects_unknown_versions() -> None:
    value = revision()
    with pytest.raises(ValidationError, match="frozen"):
        value.integration_id = UUID(int=99)
    with pytest.raises(ValidationError):
        ConnectionRevision.model_validate({**value.model_dump(), "revision_version": 2})
