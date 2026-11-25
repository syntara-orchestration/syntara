"""Shared snapshot/restore for the process-global resource-actions registry.

Centralises the private-attribute reach-ins so the three-globals tuple is
defined in exactly one place: the app-lifespan test and the authz conftest's
registry-stub fixture both restore through these helpers, so a future fourth
global in ``syntara.authz.resource_actions`` only needs adding here rather
than being tracked down in every consumer.
"""

from syntara.authz import resource_actions

RegistryState = tuple[dict[str, list[str]] | None, frozenset[str], frozenset[str]]
"""Snapshot of the process-global resource-actions registry holder."""


def snapshot_registry_state() -> RegistryState:
    """Capture the process-global resource-actions registry state."""
    return (
        resource_actions._registry,
        resource_actions._all_pairs,
        resource_actions._project_eligible,
    )


def restore_registry_state(state: RegistryState) -> None:
    """Reinstall a captured resource-actions registry state."""
    (
        resource_actions._registry,
        resource_actions._all_pairs,
        resource_actions._project_eligible,
    ) = state
