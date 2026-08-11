"""Unit tests for integrations audit handler auto-discovery."""

from syntara.audit.discovery import discover_handlers
from syntara.integrations.audit.integration_create import (
    IntegrationCreateEvent,
    IntegrationCreateHandler,
)
from syntara.integrations.audit.integration_delete import (
    IntegrationDeleteEvent,
    IntegrationDeleteHandler,
)
from syntara.integrations.audit.integration_discover import (
    IntegrationDiscoverEvent,
    IntegrationDiscoverHandler,
)
from syntara.integrations.audit.integration_refresh import (
    IntegrationRefreshEvent,
    IntegrationRefreshHandler,
)
from syntara.integrations.audit.integration_update import (
    IntegrationUpdateEvent,
    IntegrationUpdateHandler,
)
from syntara.integrations.audit.integration_validate import (
    IntegrationValidateEvent,
    IntegrationValidateHandler,
)


class TestIntegrationsAuditDiscovery:
    """Tests for automatic discovery of integrations audit handlers."""

    def test_discovers_all_handlers(self) -> None:
        """Should discover all 6 integrations audit handlers."""
        import syntara.integrations.audit

        registry = discover_handlers(syntara.integrations.audit)

        assert len(registry) == 6
        assert IntegrationCreateEvent in registry
        assert IntegrationUpdateEvent in registry
        assert IntegrationDeleteEvent in registry
        assert IntegrationValidateEvent in registry
        assert IntegrationDiscoverEvent in registry
        assert IntegrationRefreshEvent in registry

    def test_discovered_handler_types(self) -> None:
        """Should discover correct handler types for each event."""
        import syntara.integrations.audit

        registry = discover_handlers(syntara.integrations.audit)

        assert isinstance(registry[IntegrationCreateEvent], IntegrationCreateHandler)
        assert isinstance(registry[IntegrationUpdateEvent], IntegrationUpdateHandler)
        assert isinstance(registry[IntegrationDeleteEvent], IntegrationDeleteHandler)
        assert isinstance(registry[IntegrationValidateEvent], IntegrationValidateHandler)
        assert isinstance(registry[IntegrationDiscoverEvent], IntegrationDiscoverHandler)
        assert isinstance(registry[IntegrationRefreshEvent], IntegrationRefreshHandler)
