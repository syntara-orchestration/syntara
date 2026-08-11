"""User login telemetry event model.

Captures analytics when a user authenticates (every login).
Enables "active users" dashboard metrics and per-installation user counts.

Requirement: AAP-72352
"""

from sqlmodel import Field

from syntara.telemetry.events.base import BaseTelemetryEvent


class UserLoginEvent(BaseTelemetryEvent):
    """Analytics event for a user login.

    Emitted on every successful authentication (password or OIDC).
    The user_id_hash is an HMAC-SHA256 digest of the user's UUID keyed
    with a per-installation salt, ensuring no personally identifiable
    information is transmitted and preventing cross-installation correlation.
    """

    user_id_hash: str = Field(
        min_length=64,
        max_length=64,
        description="HMAC-SHA256 hash of the user UUID with per-installation salt (anonymized)",
    )
    amr: list[str] = Field(
        description="Authentication method references (e.g. ['pwd'] for password, ['fed'] for OIDC)",
    )
    idp: str = Field(
        description="Identity provider identifier (e.g. 'local' for password, provider name for OIDC)",
    )
