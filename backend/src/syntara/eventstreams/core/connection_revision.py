"""Non-secret connection change identifiers, independent of transport clients."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, field_serializer

from syntara.eventstreams.core.deduplication import DeliveryValue


class ConnectionRevision(DeliveryValue):
    """Versioned resource metadata; never accept secret values or ciphertext.

    Resource update timestamps follow the existing audit metadata conventions.
    The encrypted storage timestamp also covers updates through SecretService.
    This is a change identifier, not a live credential propagation mechanism.
    """

    revision_version: Literal[1] = 1
    integration_id: UUID
    integration_updated_at: AwareDatetime
    credential_id: UUID
    credential_updated_at: AwareDatetime
    credential_type_id: UUID
    credential_type_updated_at: AwareDatetime
    secret_id: UUID
    secret_updated_at: AwareDatetime

    @field_serializer(
        "integration_updated_at", "credential_updated_at", "credential_type_updated_at", "secret_updated_at"
    )
    def serialize_timestamp(self, value: datetime) -> str:
        """Represent equal instants identically, including subsecond changes."""
        return value.astimezone(UTC).isoformat(timespec="microseconds")

    @property
    def digest(self) -> str:
        """Return a bounded versioned hash of non-secret change identifiers."""
        encoded = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode("ascii")
        return f"connection-v1:{hashlib.sha256(encoded).hexdigest()}"
