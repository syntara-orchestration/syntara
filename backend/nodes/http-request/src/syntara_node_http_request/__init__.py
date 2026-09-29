"""SDK http-request node."""

from syntara_node_runtime.models import APIExecutorParameters, HttpRequestOutput
from syntara_node_runtime.runtime import RuntimeContext, run_async
from syntara_sdk import ActionNode, ExecutionContext

from .executor import execute_http_request_activity


class Node(ActionNode[APIExecutorParameters, HttpRequestOutput]):
    """Preserve the existing workflow contract through the SDK."""

    def __init__(self) -> None:
        """Initialize the node contract and execution state."""
        super().__init__(APIExecutorParameters, HttpRequestOutput)

    def run(self, _inputs: APIExecutorParameters, context: ExecutionContext) -> HttpRequestOutput:
        """Execute validated inputs using the portable runtime."""
        if not isinstance(context, RuntimeContext):
            message = "Use the container runner with a RuntimeContext"
            raise TypeError(message)
        result = run_async(lambda: execute_http_request_activity(context.input_config(), None), context)
        return HttpRequestOutput.model_validate(result["output"])
