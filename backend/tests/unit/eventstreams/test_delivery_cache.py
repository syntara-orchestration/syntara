"""Proof-cache fast paths, committed population and bounded Redis failure handling."""

import asyncio
import json
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from pydantic import ValidationError
from redis.exceptions import RedisError

from syntara.eventstreams.core.deduplication import DeliveryState, TerminalDelivery, TerminalProofStorage
from syntara.eventstreams.core.terminal_proof import AuthenticatedTerminalProof, TerminalProof, terminal_proof_key
from syntara.eventstreams.services import delivery_cache, delivery_cache_auth
from syntara.eventstreams.services.delivery_cache import DeliveryRedisClient, EventDeliveryTerminalLookup
from syntara.eventstreams.services.delivery_cache_auth import sign_terminal_proof, verify_terminal_proof
from tests.unit.eventstreams.test_delivery_identity import identity
from tests.unit.eventstreams.test_delivery_retention import session_factory
from tests.unit.eventstreams.test_terminal_proof import EPOCH, NOW, policy, proof, terminal


@pytest.fixture(autouse=True)
def signing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep proof fixtures independent of deployment secrets."""
    monkeypatch.setattr(delivery_cache_auth, "_derive_signing_key", lambda: b"test-only-delivery-proof-key")


def signed_proof() -> AuthenticatedTerminalProof:
    """Encode fixtures through the same authenticated wire contract as writers."""
    return sign_terminal_proof(proof())


def lookup_service(
    monkeypatch: pytest.MonkeyPatch, result: TerminalDelivery | None = None
) -> tuple[EventDeliveryTerminalLookup, AsyncMock, MagicMock, MagicMock, list[MagicMock]]:
    """Inject isolated storage and database boundaries without creating a Redis pool."""
    factory, sessions = session_factory()
    cache = AsyncMock(spec=TerminalProofStorage)
    cache.get.return_value = None
    repository = MagicMock()
    repository.lookup_terminal = AsyncMock(return_value=result)
    monkeypatch.setattr(delivery_cache, "EventDeliveryStore", MagicMock(return_value=repository))
    service = EventDeliveryTerminalLookup(factory, cache=cache, policy=policy(), now=lambda: NOW)
    return service, cache, repository, factory, sessions


async def test_valid_proof_returns_without_opening_database(monkeypatch: pytest.MonkeyPatch) -> None:
    service, cache, repository, factory, _ = lookup_service(monkeypatch)
    cache.get.return_value = signed_proof().model_dump_json()
    assert await service.lookup(identity()) == terminal()
    cache.get.assert_awaited_once_with(terminal_proof_key(identity(), EPOCH))
    factory.assert_not_called()
    repository.lookup_terminal.assert_not_awaited()
    cache.put.assert_not_awaited()


async def test_proof_expiring_during_redis_io_uses_database_without_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, cache, repository, factory, _ = lookup_service(monkeypatch, terminal())
    now = [NOW]
    monkeypatch.setattr(service, "_now", lambda: now[0])

    async def read(_key: str) -> str:
        factory.assert_not_called()
        now[0] = proof().valid_until
        return signed_proof().model_dump_json()

    cache.get.side_effect = read
    assert await service.lookup(identity()) == terminal()
    repository.lookup_terminal.assert_awaited_once_with(identity())
    factory.assert_called_once()
    cache.put.assert_not_awaited()


async def test_old_epoch_cannot_replace_current_database_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    service, cache, repository, _, _ = lookup_service(monkeypatch, terminal())
    stale = proof().model_copy(update={"cache_epoch": UUID(int=21), "temporal_run_id": "old-run"})
    cache.get.return_value = sign_terminal_proof(stale).model_dump_json()
    assert await service.lookup(identity()) == terminal()
    repository.lookup_terminal.assert_awaited_once_with(identity())
    cache.put.assert_awaited_once()
    written = AuthenticatedTerminalProof.model_validate_json(cache.put.await_args.args[1])
    assert written.cache_epoch == EPOCH
    assert written.temporal_run_id == terminal().temporal_run_id


@pytest.mark.parametrize(
    "cached",
    [None, "{", "stale-digest", b"wrong-type", "x" * 4097, TimeoutError(), OSError(), RedisError(), ValueError()],
)
async def test_missing_malformed_or_unavailable_cache_reads_postgresql(
    cached: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, cache, repository, _, _ = lookup_service(monkeypatch)
    if isinstance(cached, Exception):
        cache.get.side_effect = cached
    else:
        cache.get.return_value = cached
    assert await service.lookup(identity()) is None
    repository.lookup_terminal.assert_awaited_once_with(identity())
    cache.put.assert_not_awaited()


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": 2},
        {"cache_epoch": str(UUID(int=21))},
        {"identity_digest": "b" * 64},
        {"execution_id": str(UUID(int=99))},
        {"temporal_workflow_id": "wrong"},
        {"temporal_run_id": None},
        {"execution_confirmed_at": None},
        {"outcome": "cancelled"},
        {"valid_until": NOW.isoformat()},
        {"resolved_at": (NOW + timedelta(seconds=1)).isoformat()},
        {"payload": "not allowed"},
    ],
)
async def test_invalid_proof_never_resolves_without_database(
    changes: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    service, cache, repository, _, _ = lookup_service(monkeypatch)
    cache.get.return_value = json.dumps({**signed_proof().model_dump(mode="json"), **changes})
    assert await service.lookup(identity()) is None
    repository.lookup_terminal.assert_awaited_once_with(identity())


async def test_proof_for_another_exact_identity_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    service, cache, repository, _, _ = lookup_service(monkeypatch)
    cache.get.return_value = signed_proof().model_dump_json()
    assert await service.lookup(identity(offset=1)) is None
    repository.lookup_terminal.assert_awaited_once_with(identity(offset=1))


@pytest.mark.parametrize("changes", [{"ttl_seconds": 6}, {"retention_seconds": 6}, {"skew_seconds": 55}])
async def test_lookup_applies_current_shorter_policy(
    changes: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    service, cache, repository, _, _ = lookup_service(monkeypatch)
    service.policy = policy(**changes)
    cache.get.return_value = signed_proof().model_dump_json()
    assert await service.lookup(identity()) is None
    repository.lookup_terminal.assert_awaited_once()


@pytest.mark.parametrize("disabled", ["setting", "redis", "clock"])
async def test_disabled_or_untrusted_cache_uses_only_database(disabled: str, monkeypatch: pytest.MonkeyPatch) -> None:
    service, cache, repository, _, _ = lookup_service(monkeypatch, terminal())
    if disabled == "setting":
        service.policy = policy(enabled=False)
    elif disabled == "redis":
        service.cache = None
    else:
        monkeypatch.setattr(service, "_clock_is_safe", lambda: False)
    assert await service.lookup(identity()) == terminal()
    repository.lookup_terminal.assert_awaited_once()
    cache.get.assert_not_awaited()
    cache.put.assert_not_awaited()


async def test_scheduled_proof_is_populated_after_successful_database_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, cache, _, _, sessions = lookup_service(monkeypatch, terminal())

    async def write(key: str, encoded: str, deadline: object) -> None:
        sessions[0].begin.return_value.__aexit__.assert_awaited_once()
        sessions[0].__aexit__.assert_awaited_once()
        assert key == terminal_proof_key(identity(), EPOCH)
        parsed = AuthenticatedTerminalProof.model_validate_json(encoded)
        assert parsed == signed_proof()
        assert verify_terminal_proof(parsed)
        assert parsed.valid_until == deadline
        assert len(encoded.encode()) <= 4096

    cache.put.side_effect = write
    assert await service.lookup(identity()) == terminal()
    cache.put.assert_awaited_once()


@pytest.mark.parametrize("failure", [RedisError(), OSError(), TimeoutError(), ValueError()])
async def test_cache_write_failure_preserves_committed_resolution(
    failure: Exception, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, cache, _, _, _ = lookup_service(monkeypatch, terminal())
    cache.put.side_effect = failure
    assert await service.lookup(identity()) == terminal()


@pytest.mark.parametrize("state", [DeliveryState.FILTERED, DeliveryState.REJECTED, DeliveryState.CANCELLED])
async def test_internal_no_trigger_and_lifecycle_rows_are_never_cached(
    state: DeliveryState, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = TerminalDelivery(identity=identity(), state=state, resolved_at=NOW)
    service, cache, _, _, _ = lookup_service(monkeypatch, value)
    result = await service.lookup(identity())
    if state == DeliveryState.CANCELLED:
        assert result == value
    else:
        assert result is None
    await service.populate(identity())
    cache.put.assert_not_awaited()


@pytest.mark.parametrize("attack", ["unsigned", "forged_run", "forged_expiry", "wrong_mac", "malformed_mac"])
async def test_redis_writer_cannot_forge_terminal_resolution(attack: str, monkeypatch: pytest.MonkeyPatch) -> None:
    service, cache, repository, _, _ = lookup_service(monkeypatch)
    data = signed_proof().model_dump(mode="json")
    if attack == "unsigned":
        data.pop("mac")
    elif attack == "forged_run":
        data["temporal_run_id"] = "attacker-supplied-run"
    elif attack == "forged_expiry":
        data["valid_until"] = (proof().valid_until + timedelta(seconds=60)).isoformat()
    elif attack == "wrong_mac":
        data["mac"] = "0" * 64
    else:
        data["mac"] = "invalid"
    cache.get.return_value = json.dumps(data)
    assert await service.lookup(identity()) is None
    repository.lookup_terminal.assert_awaited_once_with(identity())
    cache.put.assert_not_awaited()


async def test_unavailable_signing_key_preserves_database_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    service, cache, repository, _, _ = lookup_service(monkeypatch, terminal())
    cache.get.return_value = signed_proof().model_dump_json()
    monkeypatch.setattr(delivery_cache_auth, "_derive_signing_key", MagicMock(side_effect=RuntimeError("no key")))
    assert await service.lookup(identity()) == terminal()
    repository.lookup_terminal.assert_awaited_once_with(identity())
    cache.put.assert_not_awaited()


@pytest.mark.parametrize("state", [DeliveryState.FILTERED, DeliveryState.REJECTED])
async def test_future_no_trigger_proofs_are_not_usable_in_m1(
    state: DeliveryState, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, cache, repository, _, _ = lookup_service(monkeypatch)
    data = proof().model_dump(mode="json")
    data.update(
        outcome=state, execution_id=None, temporal_workflow_id=None, temporal_run_id=None, execution_confirmed_at=None
    )
    cache.get.return_value = sign_terminal_proof(TerminalProof.model_validate(data)).model_dump_json()
    assert await service.lookup(identity()) is None
    repository.lookup_terminal.assert_awaited_once()
    cache.put.assert_not_awaited()


@pytest.mark.parametrize("failure_at", ["read", "commit", "session_exit"])
async def test_failed_or_uncertain_transaction_never_populates(
    failure_at: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, cache, repository, factory, _ = lookup_service(monkeypatch, terminal())
    session = MagicMock()
    session.__aenter__.return_value = session
    factory.side_effect = None
    factory.return_value = session
    if failure_at == "read":
        repository.lookup_terminal.side_effect = OSError("transaction failed")
    elif failure_at == "commit":
        session.begin.return_value.__aexit__.side_effect = OSError("uncertain commit")
    else:
        session.__aexit__.side_effect = OSError("session exit failed")
    with pytest.raises(OSError):
        await service.populate(identity())
    cache.get.assert_not_awaited()
    cache.put.assert_not_awaited()


async def test_inconsistent_database_result_cannot_publish_a_proof(monkeypatch: pytest.MonkeyPatch) -> None:
    wrong = terminal().model_copy(update={"identity": identity(offset=1)})
    service, cache, _, _, _ = lookup_service(monkeypatch, wrong)
    with pytest.raises(ValueError):
        await service.populate(identity())
    cache.put.assert_not_awaited()


async def test_population_reads_committed_evidence_without_trusting_a_supplied_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, cache, repository, _, _ = lookup_service(monkeypatch)
    await service.populate(identity())
    repository.lookup_terminal.assert_awaited_once_with(identity())
    cache.get.assert_not_awaited()
    cache.put.assert_not_awaited()


async def test_repopulation_cannot_extend_absolute_expiry_and_skips_expired_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, cache, _, _, _ = lookup_service(monkeypatch, terminal())
    now = [NOW]
    monkeypatch.setattr(service, "_now", lambda: now[0])
    await service.populate(identity())
    now[0] += timedelta(seconds=10)
    await service.populate(identity())
    first, second = cache.put.await_args_list
    assert first.args == second.args
    assert first.args[2] == proof().valid_until
    now[0] = proof().valid_until
    await service.populate(identity())
    assert cache.put.await_count == 2


@pytest.mark.parametrize("phase", ["read", "write"])
async def test_total_deadline_cancels_stalled_pool_or_command(phase: str, monkeypatch: pytest.MonkeyPatch) -> None:
    result = terminal() if phase == "write" else None
    service, cache, repository, _, _ = lookup_service(monkeypatch, result)
    service.policy = policy(timeout_seconds=0.01)
    cancelled = asyncio.Event()

    async def stalled(*_: object) -> None:
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    if phase == "read":
        cache.get.side_effect = stalled
    else:
        cache.put.side_effect = stalled
    assert await asyncio.wait_for(service.lookup(identity()), timeout=0.5) == result
    assert cancelled.is_set()
    repository.lookup_terminal.assert_awaited_once()


async def test_circuit_bypasses_errors_and_recovers_with_bounded_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    service, cache, repository, _, _ = lookup_service(monkeypatch)
    clock = [0.0]
    monkeypatch.setattr(service, "_monotonic", lambda: clock[0])
    cache.get.side_effect = OSError()
    for _ in range(4):
        assert await service.lookup(identity()) is None
    assert cache.get.await_count == 3
    clock[0] = 1.0
    assert await service.lookup(identity()) is None
    assert cache.get.await_count == 4
    clock[0] = 2.0
    assert await service.lookup(identity()) is None
    assert cache.get.await_count == 4
    clock[0] = 3.0
    cache.get.side_effect = None
    cache.get.return_value = signed_proof().model_dump_json()
    assert await service.lookup(identity()) == terminal()
    assert cache.get.await_count == 5
    assert repository.lookup_terminal.await_count == 6


async def test_single_probe_and_cancellation_allow_later_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    service, cache, _, _, _ = lookup_service(monkeypatch)
    clock = [0.0]
    monkeypatch.setattr(service, "_monotonic", lambda: clock[0])
    cache.get.side_effect = OSError()
    for _ in range(3):
        await service.lookup(identity())
    clock[0] = 1.0
    started = asyncio.Event()

    async def probe_wait(_: str) -> None:
        started.set()
        await asyncio.Event().wait()

    cache.get.side_effect = probe_wait
    task = asyncio.create_task(service.lookup(identity()))
    await asyncio.wait_for(started.wait(), timeout=0.5)
    assert await service.lookup(identity()) is None
    assert cache.get.await_count == 4
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    cache.get.side_effect = None
    cache.get.return_value = signed_proof().model_dump_json()
    assert await service.lookup(identity()) == terminal()


async def test_redis_client_uses_absolute_expiry_primitive(monkeypatch: pytest.MonkeyPatch) -> None:
    client = DeliveryRedisClient()
    write = AsyncMock()
    monkeypatch.setattr(client, "cache_set_until", write)
    key = terminal_proof_key(identity(), EPOCH)
    encoded = signed_proof().model_dump_json()
    await client.put(key, encoded, proof().valid_until)
    write.assert_awaited_once_with(key, proof().valid_until, encoded, only_if_absent=True)


@pytest.mark.parametrize("value", ["", "x" * 4097])
async def test_redis_read_is_bounded_even_for_oversized_entries(value: str) -> None:
    client = DeliveryRedisClient()
    redis = AsyncMock()
    redis.getrange.return_value = value
    client._client = redis
    key = terminal_proof_key(identity(), EPOCH)
    assert await client.get(key) == (value or None)
    redis.getrange.assert_awaited_once_with(key, 0, 4096)
    redis.get.assert_not_awaited()


async def test_read_success_does_not_hide_repeated_write_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    service, cache, _, _, _ = lookup_service(monkeypatch, terminal())
    clock = [0.0]
    monkeypatch.setattr(service, "_monotonic", lambda: clock[0])
    cache.put.side_effect = OSError()
    for _ in range(4):
        assert await service.lookup(identity()) == terminal()
    assert cache.get.await_count == 4
    assert cache.put.await_count == 3
    clock[0] = 1.0
    cache.put.side_effect = None
    assert await service.lookup(identity()) == terminal()
    assert cache.put.await_count == 4


@pytest.mark.parametrize("health", [None, OSError(), ValueError(), RuntimeError()])
async def test_unknown_clock_health_uses_postgresql_without_redis(
    health: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, cache, repository, _, _ = lookup_service(monkeypatch, terminal())
    check = MagicMock()
    if isinstance(health, Exception):
        check.side_effect = health
    else:
        check.return_value = health
    monkeypatch.setattr(service, "_clock_is_safe", check)
    assert await service.lookup(identity()) == terminal()
    repository.lookup_terminal.assert_awaited_once()
    cache.get.assert_not_awaited()
    cache.put.assert_not_awaited()


async def test_clock_assumption_is_rechecked_after_cache_io(monkeypatch: pytest.MonkeyPatch) -> None:
    service, cache, repository, _, _ = lookup_service(monkeypatch)
    cache.get.return_value = signed_proof().model_dump_json()
    monkeypatch.setattr(service, "_clock_is_safe", MagicMock(side_effect=[True, False]))
    assert await service.lookup(identity()) is None
    repository.lookup_terminal.assert_awaited_once()


async def test_old_success_cannot_close_a_circuit_opened_by_newer_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, cache, repository, _, _ = lookup_service(monkeypatch)
    monkeypatch.setattr(service, "_monotonic", lambda: 0.0)
    started = asyncio.Event()
    release = asyncio.Event()

    async def old_read(_: str) -> str:
        started.set()
        await release.wait()
        return signed_proof().model_dump_json()

    cache.get.side_effect = old_read
    task = asyncio.create_task(service.lookup(identity()))
    try:
        await asyncio.wait_for(started.wait(), timeout=0.5)
        cache.get.side_effect = OSError()
        for _ in range(3):
            assert await service.lookup(identity()) is None
        release.set()
        assert await asyncio.wait_for(task, timeout=0.5) == terminal()
        assert await service.lookup(identity()) is None
        assert cache.get.await_count == 4
        assert repository.lookup_terminal.await_count == 4
    finally:
        release.set()
        if not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task


async def test_oversized_proof_is_not_written(monkeypatch: pytest.MonkeyPatch) -> None:
    # Exercise the output bound even with an identity larger than a real source
    # generation column can hold. No such data is written to a database.
    value = identity().model_copy(update={"source_generation": 10**4000})
    result = terminal().model_copy(update={"identity": value, "execution_id": value.execution_id})
    service, cache, repository, _, _ = lookup_service(monkeypatch, result)
    await service.populate(value)
    repository.lookup_terminal.assert_awaited_once_with(value)
    cache.put.assert_not_awaited()
    assert service._write_circuit.failures == 0


async def test_mac_size_overflow_skips_population_without_opening_write_circuit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Use a synthetic generation larger than the database column can hold to
    # exercise the wire-size boundary without writing it to a database.
    digits_to_add = 4090 - len(proof().model_dump_json().encode())
    value = identity().model_copy(update={"source_generation": 10**digits_to_add})
    unsigned = TerminalProof.model_validate(
        {
            **proof().model_dump(),
            "identity": value,
            "identity_digest": value.digest,
            "execution_id": value.execution_id,
            "temporal_workflow_id": value.temporal_workflow_id,
        }
    )
    assert len(unsigned.model_dump_json().encode()) <= 4096
    with pytest.raises(ValidationError, match="serialized entry limit"):
        sign_terminal_proof(unsigned)

    result = terminal().model_copy(update={"identity": value, "execution_id": value.execution_id})
    service, cache, repository, _, _ = lookup_service(monkeypatch, result)
    warning = MagicMock()
    monkeypatch.setattr(delivery_cache.logger, "warning", warning)
    for _ in range(4):
        await service.populate(value)
    assert repository.lookup_terminal.await_count == 4
    cache.put.assert_not_awaited()
    warning.assert_not_called()
    assert service._write_circuit.failures == 0
    assert service._write_circuit.retry_at == 0
    assert not service._write_circuit.probe_inflight

    repository.lookup_terminal.return_value = terminal()
    await service.populate(identity())
    cache.put.assert_awaited_once()
