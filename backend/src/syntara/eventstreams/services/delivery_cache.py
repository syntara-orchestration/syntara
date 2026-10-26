"""Optional bounded terminal proofs; PostgreSQL owns all original resolution evidence."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from pydantic import ValidationError
from redis.exceptions import RedisError
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.cache.base import BaseRedisClient, redis_error_handler
from syntara.core.cache.cache_client import CacheMixin
from syntara.core.constants import EventDeliveryDefaults
from syntara.eventstreams.core.deduplication import (
    DeliveryIdentity,
    DeliveryState,
    TerminalDelivery,
    TerminalProofStorage,
)
from syntara.eventstreams.core.terminal_proof import AuthenticatedTerminalProof, TerminalProof, terminal_proof_key
from syntara.eventstreams.services.deduplication_store import EventDeliveryStore
from syntara.eventstreams.services.delivery_cache_auth import sign_terminal_proof, verify_terminal_proof
from syntara.eventstreams.services.delivery_cache_policy import DeliveryEvidencePolicy

logger = structlog.stdlib.get_logger(__name__)


@dataclass
class _CacheCircuit:
    """Constant-sized local availability state, independent for reads and writes."""

    failures: int = 0
    retry_at: float = 0.0
    probe_inflight: bool = False
    probe_delay: float = float(EventDeliveryDefaults.TERMINAL_CACHE_PROBE_INITIAL_SECONDS)
    generation: int = 0

    def permit(self, now: float) -> bool:
        if self.failures < EventDeliveryDefaults.TERMINAL_CACHE_FAILURE_THRESHOLD:
            return True
        if self.probe_inflight or now < self.retry_at:
            return False
        self.probe_inflight = True
        return True

    def succeeded(self, generation: int) -> None:
        if generation != self.generation:
            return
        if self.failures == EventDeliveryDefaults.TERMINAL_CACHE_FAILURE_THRESHOLD:
            self.generation += 1
        self.failures = 0
        self.retry_at = 0.0
        self.probe_delay = float(EventDeliveryDefaults.TERMINAL_CACHE_PROBE_INITIAL_SECONDS)

    def failed(self, now: float, generation: int) -> None:
        if generation != self.generation:
            return
        self.failures = min(self.failures + 1, EventDeliveryDefaults.TERMINAL_CACHE_FAILURE_THRESHOLD)
        if self.failures == EventDeliveryDefaults.TERMINAL_CACHE_FAILURE_THRESHOLD:
            # Requests already in flight cannot close or postpone this circuit.
            self.generation += 1
            self.retry_at = now + self.probe_delay
            self.probe_delay = min(self.probe_delay * 2, EventDeliveryDefaults.TERMINAL_CACHE_PROBE_MAX_SECONDS)


class DeliveryRedisClient(BaseRedisClient, CacheMixin):
    """Inject one process-owned client; never instantiate per subscription or lookup."""

    _client_name = "event_delivery"

    async def get(self, key: str) -> str | None:
        """Read a disposable serialized proof, not a claim or an absence marker."""
        client = self._ensure_connected()
        async with redis_error_handler("event_delivery_proof_get", key=key):
            # GETRANGE's end is inclusive: the extra byte exposes oversized
            # entries without downloading an unbounded value from Redis.
            result: str = await client.getrange(key, 0, EventDeliveryDefaults.TERMINAL_CACHE_MAX_ENTRY_BYTES)
            return result or None

    async def put(self, key: str, value: str, valid_until: datetime) -> None:
        """Retries use the proof's original absolute expiry, never a relative TTL."""
        await self.cache_set_until(key, valid_until, value, only_if_absent=True)


class EventDeliveryTerminalLookup:
    """Validate proofs before any database session; populate only committed reads.

    Callers must first establish source/partition eligibility and shared outage
    and recovery gates. A proof does not authorize Kafka ownership or a commit.
    Share this provider/client per process for bounded circuit state; no local
    proof mirror, write queue or background refresh is maintained.
    """

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        *,
        cache: TerminalProofStorage | None = None,
        policy: DeliveryEvidencePolicy | None = None,
        now: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        clock_is_safe: Callable[[], bool] | None = None,
    ) -> None:
        """Inject storage, common policy and optional runtime clock-bound health.

        The explicit deployment clock bound is required when enabled. A runtime
        clock-health callback may revoke that assumption and bypass Redis.
        """
        self.session_factory = session_factory
        self.cache = cache
        self.policy = DeliveryEvidencePolicy.from_settings() if policy is None else policy
        self._now: Callable[[], datetime] = (lambda: datetime.now(UTC)) if now is None else now
        self._monotonic = monotonic
        self._clock_is_safe: Callable[[], bool] = (lambda: True) if clock_is_safe is None else clock_is_safe
        self._read_circuit = _CacheCircuit()
        self._write_circuit = _CacheCircuit()

    def _enabled(self) -> bool:
        if not self.policy.enabled or self.cache is None:
            return False
        try:
            return self._clock_is_safe() is True
        except (OSError, ValueError, RuntimeError):
            logger.warning("event_delivery_terminal_proof_clock_unavailable")
            return False

    async def _operation[T](self, operation: Callable[[], Awaitable[T]], circuit: _CacheCircuit) -> T | None:
        if not self._enabled() or not circuit.permit(self._monotonic()):
            return None
        probe = circuit.probe_inflight
        generation = circuit.generation
        try:
            # Includes lazy connection/pool acquisition, all retries and validation.
            async with asyncio.timeout(self.policy.timeout_seconds):
                result = await operation()
            circuit.succeeded(generation)
            return result
        except (RedisError, OSError, TimeoutError, ValueError, TypeError, RuntimeError):
            circuit.failed(self._monotonic(), generation)
            logger.warning("event_delivery_terminal_proof_cache_unavailable")
            return None
        finally:
            if probe:
                circuit.probe_inflight = False

    async def _read_proof(self, identity: DeliveryIdentity) -> TerminalDelivery | None:
        async def read() -> TerminalDelivery | None:
            if self.cache is None or self.policy.cache_epoch is None:
                return None
            raw = await self.cache.get(terminal_proof_key(identity, self.policy.cache_epoch))
            if (
                not isinstance(raw, str)
                or len(raw) > EventDeliveryDefaults.TERMINAL_CACHE_MAX_ENTRY_BYTES
                or len(raw.encode("utf-8")) > EventDeliveryDefaults.TERMINAL_CACHE_MAX_ENTRY_BYTES
            ):
                return None
            proof = AuthenticatedTerminalProof.model_validate_json(raw)
            if (
                not verify_terminal_proof(proof)
                or not self._enabled()
                or not self.policy.trusts(proof, identity, self._now())
            ):
                return None
            return proof.terminal()

        return await self._operation(read, self._read_circuit)

    async def _populate_terminal(self, terminal: TerminalDelivery) -> None:
        # No-trigger discard safeguards and author-accessible rejection logging
        # are not available in M1. Internal rejected rows never become proofs.
        if terminal.state != DeliveryState.SCHEDULED:
            return

        async def write() -> None:
            if self.cache is None or self.policy.cache_epoch is None:
                return
            deadline = self.policy.proof_deadline(terminal.resolved_at)
            now = self._now()
            if now.tzinfo is None or terminal.resolved_at > now or deadline <= now:
                return
            try:
                proof = TerminalProof(
                    schema_version=1,
                    cache_epoch=self.policy.cache_epoch,
                    identity=terminal.identity,
                    identity_digest=terminal.identity.digest,
                    outcome=DeliveryState.SCHEDULED,
                    resolved_at=terminal.resolved_at,
                    valid_until=deadline,
                    execution_id=terminal.execution_id,
                    temporal_workflow_id=terminal.identity.temporal_workflow_id,
                    temporal_run_id=terminal.temporal_run_id,
                    execution_confirmed_at=terminal.execution_confirmed_at,
                )
                encoded = sign_terminal_proof(proof).model_dump_json()
            except ValidationError:
                # An uncacheable value (including MAC size overhead) says
                # nothing about storage availability. Keep the circuit closed.
                return
            if len(encoded.encode("utf-8")) > EventDeliveryDefaults.TERMINAL_CACHE_MAX_ENTRY_BYTES:
                return
            await self.cache.put(terminal_proof_key(terminal.identity, self.policy.cache_epoch), encoded, deadline)

        await self._operation(write, self._write_circuit)

    async def _committed_terminal(self, identity: DeliveryIdentity) -> TerminalDelivery | None:
        async with self.session_factory() as session, session.begin():
            terminal = await EventDeliveryStore(session).lookup_terminal(identity)
        # Both contexts have exited successfully. Failed or uncertain commits
        # propagate without publishing a proof, even if SELECT returned a value.
        if terminal is not None:
            terminal = TerminalDelivery.model_validate(terminal.model_dump())
            if terminal.identity != identity:
                msg = "Committed terminal evidence does not match the requested identity"
                raise ValueError(msg)
            if terminal.state in {DeliveryState.FILTERED, DeliveryState.REJECTED}:
                # Existing internal rows are not evidence that the deferred
                # discard safeguards have been met. Preserve them, fail closed.
                return None
            await self._populate_terminal(terminal)
        return terminal

    async def lookup(self, identity: DeliveryIdentity) -> TerminalDelivery | None:
        """Return a trusted proof without delivery-row/Temporal calls, else read PostgreSQL.

        None means no usable terminal proof, never authoritative row absence or
        permission to admit new work. Unresolved and ungated rows remain retained.
        """
        terminal = await self._read_proof(identity)
        return terminal if terminal is not None else await self._committed_terminal(identity)

    async def populate(self, identity: DeliveryIdentity) -> None:
        """Post-commit scheduling hook: independently read committed evidence.

        Accept identity rather than a provisional repository result, so a caller
        cannot accidentally turn failed/stale finalization into a cached proof.
        """
        if self._enabled():
            await self._committed_terminal(identity)
