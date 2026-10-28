"""Retention orchestration and fail-closed verification without external services."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.config.base import Settings
from syntara.eventstreams.core.deduplication import (
    CleanupCandidate,
    CommittedPositionUnavailableError,
    CommittedPositionVerifier,
)
from syntara.eventstreams.services import delivery_cache_policy, delivery_retention_service
from syntara.eventstreams.services.delivery_retention_service import EventDeliveryRetentionService
from tests.unit.eventstreams.test_deduplication_store import delivery
from tests.unit.eventstreams.test_delivery_identity import identity
from tests.unit.eventstreams.test_terminal_proof import EPOCH, NOW, policy


def session_factory() -> tuple[MagicMock, list[MagicMock]]:
    """Create a new isolated session/context manager on every invocation."""
    sessions: list[MagicMock] = []

    def create() -> MagicMock:
        session = MagicMock(spec=AsyncSession)
        session.__aenter__.return_value = session
        sessions.append(session)
        return session

    return MagicMock(side_effect=create), sessions


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "3600"])
def test_retention_requires_positive_integer(value: int) -> None:
    """Invalid injected retention cannot bypass Settings validation."""
    factory = MagicMock()
    with pytest.raises(ValueError, match="positive integer"):
        EventDeliveryRetentionService(factory, retention_seconds=value)
    factory.assert_not_called()


async def test_absent_verifier_retains_without_opening_sessions() -> None:
    """No adapter verifier means no cleanup permission."""
    factory = MagicMock()
    service = EventDeliveryRetentionService(factory, retention_seconds=3600)
    assert not await service.cleanup_one(identity())
    assert await service.cleanup(limit=10) == 0
    factory.assert_not_called()


@pytest.mark.parametrize("verification", [False, TimeoutError(), CommittedPositionUnavailableError()])
async def test_uncertainty_retains_evidence(verification: object, monkeypatch: pytest.MonkeyPatch) -> None:
    """Unavailable or negative evidence never enters a deletion transaction."""
    factory, sessions = session_factory()
    verifier = AsyncMock(spec=CommittedPositionVerifier)
    if isinstance(verification, Exception):
        verifier.is_committed_beyond.side_effect = verification
    else:
        verifier.is_committed_beyond.return_value = verification
    service = EventDeliveryRetentionService(factory, verifier=verifier, retention_seconds=3600)
    candidate = CleanupCandidate(identity=identity(), resolved_at=datetime.now(UTC), evidence_revision=0)
    monkeypatch.setattr(service, "_candidate", AsyncMock(return_value=candidate))
    assert not await service.cleanup_one(identity())
    assert len(sessions) == 1
    sessions[0].delete.assert_not_awaited()


async def test_verification_runs_outside_transactions(monkeypatch: pytest.MonkeyPatch) -> None:
    """A slow broker call holds no SQL session or transaction open."""
    factory, sessions = session_factory()
    candidate = CleanupCandidate(identity=identity(), resolved_at=datetime.now(UTC), evidence_revision=0)
    verifier = AsyncMock(spec=CommittedPositionVerifier)

    async def verify(_: object) -> bool:
        assert len(sessions) == 1
        sessions[0].begin.return_value.__aexit__.assert_awaited_once()
        sessions[0].__aexit__.assert_awaited_once()
        return True

    verifier.is_committed_beyond.side_effect = verify
    service = EventDeliveryRetentionService(factory, verifier=verifier, retention_seconds=3600)
    monkeypatch.setattr(service, "_candidate", AsyncMock(return_value=candidate))
    assert await service.cleanup_one(identity())
    assert len(sessions) == 2
    sessions[1].delete.assert_awaited_once()


async def test_recovery_revision_change_invalidates_verification(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hold registered and released during verification still fences deletion."""
    factory, sessions = session_factory()
    candidate = CleanupCandidate(identity=identity(), resolved_at=datetime.now(UTC), evidence_revision=0)
    changed = candidate.model_copy(update={"evidence_revision": 2})
    verifier = AsyncMock(spec=CommittedPositionVerifier)
    verifier.is_committed_beyond.return_value = True
    service = EventDeliveryRetentionService(factory, verifier=verifier, retention_seconds=3600)
    monkeypatch.setattr(service, "_candidate", AsyncMock(side_effect=[candidate, changed]))
    assert not await service.cleanup_one(identity())
    assert len(sessions) == 2
    sessions[1].delete.assert_not_awaited()


async def test_ineligible_or_held_evidence_is_not_verified(monkeypatch: pytest.MonkeyPatch) -> None:
    """Early eligibility failure cannot be replaced by a positive broker answer."""
    factory, _ = session_factory()
    verifier = AsyncMock(spec=CommittedPositionVerifier)
    service = EventDeliveryRetentionService(factory, verifier=verifier, retention_seconds=3600)
    monkeypatch.setattr(service, "_candidate", AsyncMock(return_value=None))
    assert not await service.cleanup_one(identity())
    verifier.is_committed_beyond.assert_not_awaited()


@pytest.mark.parametrize("limit", [0, -1, 101, True])
async def test_cleanup_is_bounded(limit: int) -> None:
    """Batch limits apply even when no committed-position verifier is installed."""
    service = EventDeliveryRetentionService(MagicMock(), retention_seconds=3600)
    with pytest.raises(ValueError, match="batch size"):
        await service.cleanup(limit=limit)


def test_cleanup_rejects_a_conflicting_shared_retention_policy() -> None:
    with pytest.raises(ValueError, match="match the shared"):
        EventDeliveryRetentionService(MagicMock(), retention_seconds=10, policy=policy(retention_seconds=3600))


def test_enabled_cleanup_cannot_implicitly_shorten_deployment_retention(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        event_delivery_cache_enabled=True,
        event_delivery_cache_epoch=EPOCH,
        event_delivery_cache_clock_error_bound_seconds=0.25,
    )
    monkeypatch.setattr(delivery_cache_policy, "get_settings", lambda: settings)
    with pytest.raises(ValueError, match="deployment retention"):
        EventDeliveryRetentionService(MagicMock(), retention_seconds=10)
    service = EventDeliveryRetentionService(MagicMock())
    assert service.retention_seconds == settings.event_delivery_retention_seconds
    assert service.policy.enabled


@pytest.mark.parametrize("at_deadline", [False, True])
async def test_cleanup_retains_evidence_through_proof_expiry_and_skew(
    monkeypatch: pytest.MonkeyPatch, *, at_deadline: bool
) -> None:
    shared = policy(ttl_seconds=120, retention_seconds=30)
    row = delivery()
    row.state = "scheduled"
    row.resolved_at = NOW
    now = shared.proof_deadline(NOW) if at_deadline else NOW + timedelta(seconds=10)
    subscription = MagicMock(id=identity().subscription_id, workflow_id=identity().workflow_id)
    source = MagicMock()
    monkeypatch.setattr(
        delivery_retention_service, "lock_source_lifecycle", AsyncMock(return_value=(subscription, source))
    )
    session = MagicMock(spec=AsyncSession)
    row_result = MagicMock()
    row_result.one_or_none.return_value = row
    clock_result = MagicMock()
    clock_result.one.return_value = now
    session.exec.side_effect = [row_result, clock_result]
    service = EventDeliveryRetentionService(MagicMock(), policy=shared)
    assert await service._candidate(session, identity()) is None
    session.delete.assert_not_awaited()
