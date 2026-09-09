"""Settings shared by scheduler wake-up PoC roles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from os import getenv


@dataclass(frozen=True)
class POCSettings:
    database_url: str = "sqlite+aiosqlite:///./scheduler-wakeup-poc.db"
    owner_id: str = "scheduler-1"
    claim_batch_size: int = 32
    dispatch_limit: int = 128
    lease_seconds: float = 10.0
    recovery_seconds: float = 5.0
    recovery_enabled: bool = True

    @property
    def lease_duration(self) -> timedelta:
        return timedelta(seconds=self.lease_seconds)

    @classmethod
    def from_environment(cls) -> POCSettings:
        return cls(
            database_url=getenv("POC_DATABASE_URL", cls.database_url),
            owner_id=getenv("POC_OWNER_ID", cls.owner_id),
            claim_batch_size=int(getenv("POC_CLAIM_BATCH_SIZE", "32")),
            dispatch_limit=int(getenv("POC_DISPATCH_LIMIT", "128")),
            lease_seconds=float(getenv("POC_LEASE_SECONDS", "10")),
            recovery_seconds=float(getenv("POC_RECOVERY_SECONDS", "5")),
            recovery_enabled=getenv("POC_RECOVERY", "on").lower() == "on",
        )
