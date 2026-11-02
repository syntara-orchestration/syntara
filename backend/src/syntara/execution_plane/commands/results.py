"""Typed results returned by AO command handlers."""

from dataclasses import dataclass, field

from execution_plane_client.commands.credentials import CredentialResolution
from execution_plane_client.handlers import HandlingResult
from execution_plane_client.protocol import TransportReceipt


@dataclass(frozen=True)
class AOCommandResult(HandlingResult):
    """A command-specific wire response and optional affected resource."""

    body: TransportReceipt | CredentialResolution = field(kw_only=True)
