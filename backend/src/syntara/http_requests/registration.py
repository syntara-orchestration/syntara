"""HTTP request domain activity registrations."""

from syntara.http_requests.activities import execute_http_request_activity
from syntara.workflow_runtime.providers import ActivityProvider, ActivityProviderContext
from syntara.workflow_runtime.registry import ActivityDefinition, ActivityRegistry


def _register_http_request_activities(registry: ActivityRegistry) -> None:
    """Install the synchronous HTTP request provider."""
    registry.register(ActivityDefinition("http_request.execute", 1, execute_http_request_activity))


class HttpRequestActivityProvider:
    """Register HTTP request activities without requiring worker dependencies."""

    def __init__(self, context: ActivityProviderContext) -> None:
        """Accept the common provider context for a uniform provider contract."""
        del context

    def register(self, registry: ActivityRegistry) -> None:
        """Register HTTP request activity definitions."""
        _register_http_request_activities(registry)


def create_activity_provider(context: ActivityProviderContext) -> ActivityProvider:
    """Create the HTTP request domain provider for worker startup discovery."""
    return HttpRequestActivityProvider(context)


def register_http_request_activities(registry: ActivityRegistry) -> None:
    """Register explicitly for tests and embedded worker integrations."""
    _register_http_request_activities(registry)
