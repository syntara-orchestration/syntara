"""Install only the Execution Plane commands handled by AO."""

from execution_plane_client.catalog import CommandCatalog
from execution_plane_client.registry import CommandRegistry

from syntara.execution_plane.commands.completion import CompletionCommandHandler
from syntara.execution_plane.commands.context import AOCommandContext
from syntara.execution_plane.commands.credentials import CredentialResolveCommandHandler


def build_ao_registry() -> CommandRegistry[AOCommandContext]:
    """Construct the stateless AO handler registry."""
    catalog = CommandCatalog()
    registry = CommandRegistry[AOCommandContext]()
    registry.register(catalog.definition("work.execute.completed", 1), CompletionCommandHandler())
    registry.register(catalog.definition("credential.resolve", 1), CredentialResolveCommandHandler())
    return registry
