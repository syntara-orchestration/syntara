"""Install only the Execution Plane commands handled by AO."""

from execution_plane_client.catalog import CommandCatalog
from execution_plane_client.errors import UnsupportedCommand
from execution_plane_client.registry import CommandRegistry

from syntara.core.config.base import get_settings
from syntara.execution_plane.commands.completion import CompletionCommandHandler
from syntara.execution_plane.commands.context import AOCommandContext
from syntara.execution_plane.commands.credentials import (
    CredentialResolveClusterCommandHandler,
    CredentialResolveWorkloadCommandHandler,
)


def build_ao_registry() -> CommandRegistry[AOCommandContext]:
    """Construct the stateless AO handler registry."""
    catalog = CommandCatalog()
    registry = CommandRegistry[AOCommandContext]()
    registry.register(catalog.definition("work.execute.completed", 1), CompletionCommandHandler())
    try:
        agent_operation = catalog.definition("agent.operation", 1)
    except UnsupportedCommand:
        if get_settings().agent_runtime_enabled:
            message = "Agent Runtime is enabled, but execution-plane-client does not support agent.operation"
            raise RuntimeError(message) from None
    else:
        from syntara.execution_plane.commands.agent_operations import (  # noqa: PLC0415 -- older client versions lack the command contract.
            AgentOperationCommandHandler,
        )

        registry.register(agent_operation, AgentOperationCommandHandler())
    registry.register(catalog.definition("credential.resolve.cluster", 1), CredentialResolveClusterCommandHandler())
    registry.register(
        catalog.definition("credential.resolve.workload", 1),
        CredentialResolveWorkloadCommandHandler(),
    )
    return registry
