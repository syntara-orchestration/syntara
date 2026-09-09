"""Transport-independent contracts for the scheduler wake-up PoCs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import UUID

from sqlmodel import Field, SQLModel


class WakeHint(SQLModel):
    """An advisory signal that a queue may have eligible work."""

    version: Literal[1] = 1
    event_id: UUID
    queue: str = Field(min_length=1, max_length=255)


class PublishReceipt(SQLModel):
    """What a wake-up transport accepted, rather than what it scheduled."""

    acceptance: Literal["volatile", "durable"]
    transport_ref: str | None = None


class SubmitTask(SQLModel):
    """A request to put one sample task onto a logical queue."""

    queue: str = Field(min_length=1, max_length=255)
    idempotency_key: str = Field(min_length=1, max_length=255)
    task: dict[str, Any]
    not_before: datetime | None = None
    deadline: datetime | None = None


class Submission(SQLModel):
    execution_id: UUID
    state: str
    created: bool
    wake_event_id: UUID | None = None


class Claim(SQLModel):
    execution_id: UUID
    attempt_id: UUID
    queue: str
    fencing_token: int
    owner_id: str
    lease_expires_at: datetime


class PassResult(SQLModel):
    claimed_count: int
    deferred_count: int
    immediate_more: bool
    next_due_at: datetime | None = None


class ExecutionStore(Protocol):
    async def enqueue(self, request: SubmitTask) -> Submission: ...

    async def claim_ready(self, queue: str, owner: str, limit: int) -> list[Claim]: ...

    async def renew(self, claim: Claim) -> bool: ...

    async def complete(self, claim: Claim, result: dict[str, Any]) -> bool: ...

    async def recover_expired(self, queue: str, limit: int) -> int: ...


class WakePublisher(Protocol):
    async def publish(self, hint: WakeHint) -> PublishReceipt: ...


class Scheduler(Protocol):
    async def run_pass(self, queue: str) -> PassResult: ...
