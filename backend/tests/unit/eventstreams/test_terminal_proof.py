"""Proof identity, historical scheduling evidence and retention-bounded validity."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from syntara.eventstreams.core.deduplication import DeliveryState, TerminalDelivery
from syntara.eventstreams.core.terminal_proof import TerminalProof, terminal_proof_key
from syntara.eventstreams.services.delivery_cache_policy import DeliveryEvidencePolicy
from tests.unit.eventstreams.test_delivery_identity import identity

NOW = datetime(2026, 10, 26, tzinfo=UTC)
EPOCH = UUID(int=20)


def policy(**changes: object) -> DeliveryEvidencePolicy:
    """Explicit test trust inputs; no production clock or restore guarantee."""
    return DeliveryEvidencePolicy.model_validate(
        {"enabled": True, "cache_epoch": EPOCH, "clock_error_bound_seconds": 0.25, **changes}
    )


def terminal() -> TerminalDelivery:
    """A hypothetical committed scheduling result, never a Temporal RPC result."""
    value = identity()
    return TerminalDelivery(
        identity=value,
        state=DeliveryState.SCHEDULED,
        resolved_at=NOW - timedelta(seconds=5),
        execution_id=value.execution_id,
        temporal_run_id="confirmed-run",
        execution_confirmed_at=NOW - timedelta(seconds=5),
    )


def proof() -> TerminalProof:
    """Construct the complete bounded scheduling proof used by provider tests."""
    value = terminal()
    return TerminalProof(
        schema_version=1,
        cache_epoch=EPOCH,
        identity=value.identity,
        identity_digest=value.identity.digest,
        outcome=DeliveryState.SCHEDULED,
        resolved_at=value.resolved_at,
        valid_until=policy().proof_deadline(value.resolved_at),
        execution_id=value.execution_id,
        temporal_workflow_id=value.identity.temporal_workflow_id,
        temporal_run_id=value.temporal_run_id,
        execution_confirmed_at=value.execution_confirmed_at,
    )


def test_epoch_keys_leave_durable_identity_unchanged() -> None:
    value = identity()
    before = (value.canonical_bytes(), value.digest, value.execution_id, value.temporal_workflow_id)
    assert terminal_proof_key(value, EPOCH) == f"syntara:eventstreams:terminal:v1:{EPOCH}:{value.digest}"
    assert terminal_proof_key(value, EPOCH) != terminal_proof_key(value, UUID(int=21))
    assert (value.canonical_bytes(), value.digest, value.execution_id, value.temporal_workflow_id) == before
    assert "cache_epoch" not in value.model_dump()
    with pytest.raises(ValueError, match="nonzero"):
        terminal_proof_key(value, UUID(int=0))


def test_complete_proof_round_trip() -> None:
    value = TerminalProof.model_validate_json(proof().model_dump_json())
    assert policy().trusts(value, identity(), NOW)
    assert value.terminal() == terminal()


@pytest.mark.parametrize(
    "field",
    [
        "schema_version",
        "cache_epoch",
        "identity",
        "identity_digest",
        "outcome",
        "resolved_at",
        "valid_until",
        "execution_id",
        "temporal_workflow_id",
        "temporal_run_id",
        "execution_confirmed_at",
    ],
)
def test_scheduled_proof_requires_every_evidence_field(field: str) -> None:
    data = proof().model_dump(mode="json")
    data.pop(field)
    with pytest.raises(ValidationError):
        TerminalProof.model_validate(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", 2),
        ("schema_version", True),
        ("schema_version", "1"),
        ("identity_digest", "b" * 64),
        ("cache_epoch", str(UUID(int=0))),
        ("execution_id", str(UUID(int=99))),
        ("temporal_workflow_id", "wrong"),
        ("temporal_run_id", ""),
        ("temporal_run_id", " "),
        ("temporal_run_id", "x" * 256),
        ("execution_confirmed_at", NOW.isoformat()),
        ("resolved_at", "2026-10-26T00:00:00"),
        ("valid_until", (NOW - timedelta(seconds=6)).isoformat()),
        ("outcome", "in_progress"),
        ("outcome", "cancelled"),
        ("payload", {"secret": "not allowed"}),
        ("claim_token", str(UUID(int=30))),
        ("retry_error", "unavailable"),
        ("execution_status", "running"),
    ],
)
def test_malformed_or_inconsistent_proofs_are_rejected(field: str, value: object) -> None:
    data = proof().model_dump(mode="json")
    data[field] = value
    with pytest.raises(ValidationError):
        TerminalProof.model_validate(data)


def test_proof_value_enforces_its_serialized_size_limit() -> None:
    value = identity().model_copy(update={"source_generation": 10**4000})
    data = proof().model_dump()
    data.update(
        identity=value,
        identity_digest=value.digest,
        execution_id=value.execution_id,
        temporal_workflow_id=value.temporal_workflow_id,
    )
    with pytest.raises(ValidationError, match="serialized entry limit"):
        TerminalProof.model_validate(data)


def test_wrong_request_epoch_future_resolution_and_expiry_are_not_trusted() -> None:
    value = proof()
    assert not policy().trusts(value, identity(offset=1), NOW)
    assert not policy(cache_epoch=UUID(int=21)).trusts(value, identity(), NOW)
    assert not policy().trusts(value, identity(), value.resolved_at - timedelta(microseconds=1))
    assert not policy().trusts(value, identity(), value.valid_until)
    assert not policy().trusts(value, identity(), NOW.replace(tzinfo=None))


@pytest.mark.parametrize("changes", [{"ttl_seconds": 6}, {"retention_seconds": 6}, {"skew_seconds": 55}])
def test_current_shorter_settings_clamp_old_proofs(changes: dict[str, object]) -> None:
    assert policy().trusts(proof(), identity(), NOW)
    assert not policy(**changes).trusts(proof(), identity(), NOW)


def test_longer_settings_cannot_extend_an_existing_proof() -> None:
    assert not policy(ttl_seconds=120, retention_seconds=7200).trusts(proof(), identity(), proof().valid_until)


def test_attested_clock_bound_is_covered_by_skew_without_double_subtraction() -> None:
    smaller_bound = policy(clock_error_bound_seconds=0.1)
    larger_bound = policy(clock_error_bound_seconds=0.9)
    expected = proof().resolved_at + timedelta(seconds=59)
    assert smaller_bound.proof_deadline(proof().resolved_at) == expected
    assert larger_bound.proof_deadline(proof().resolved_at) == expected
    for shared in (smaller_bound, larger_bound):
        assert shared.trusts(proof(), identity(), expected - timedelta(microseconds=1))
        assert not shared.trusts(proof(), identity(), expected)


@pytest.mark.parametrize("state", [DeliveryState.FILTERED, DeliveryState.REJECTED])
def test_future_no_trigger_values_are_representable_but_not_trusted_in_m1(state: DeliveryState) -> None:
    data = proof().model_dump()
    data.update(
        outcome=state, execution_id=None, temporal_workflow_id=None, temporal_run_id=None, execution_confirmed_at=None
    )
    value = TerminalProof.model_validate(data)
    assert value.terminal().state == state
    assert not policy().trusts(value, identity(), NOW)


@pytest.mark.parametrize(("ttl", "retention", "skew"), [(60, 3600, 1), (120, 30, 2), (10, 10, 0.5)])
def test_cleanup_always_follows_proof_expiry_plus_clock_margin(ttl: int, retention: int, skew: float) -> None:
    shared = policy(ttl_seconds=ttl, retention_seconds=retention, skew_seconds=skew)
    assert shared.proof_deadline(NOW) + timedelta(seconds=skew) <= shared.cleanup_after(NOW)


@pytest.mark.parametrize(
    "changes",
    [
        {"cache_epoch": None},
        {"clock_error_bound_seconds": None},
        {"clock_error_bound_seconds": 1},
        {"ttl_seconds": 1},
        {"retention_seconds": 1},
        {"timeout_seconds": float("nan")},
    ],
)
def test_injected_policies_fail_closed_without_trust(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        policy(**changes)
