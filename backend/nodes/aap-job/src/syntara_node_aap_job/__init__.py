"""SDK aap-job node."""

from syntara_node_runtime.models import AAPJobTemplateExecutorParameters, AAPJobTemplateOutput
from syntara_node_runtime.runtime import RuntimeContext, run_async
from syntara_sdk import ExecutionContext, TaskNode

from .executor import execute_aap_job_template_activity


class Node(TaskNode[AAPJobTemplateExecutorParameters, AAPJobTemplateOutput]):
    """Preserve the existing workflow contract through the SDK."""

    def __init__(self) -> None:
        """Initialize the node contract and execution state."""
        super().__init__(AAPJobTemplateExecutorParameters, AAPJobTemplateOutput)

    def run(self, _inputs: AAPJobTemplateExecutorParameters, context: ExecutionContext) -> AAPJobTemplateOutput:
        """Execute validated inputs using the portable runtime."""
        if not isinstance(context, RuntimeContext):
            message = "Use the container runner with a RuntimeContext"
            raise TypeError(message)
        result = run_async(
            lambda: execute_aap_job_template_activity(
                context.input_config(),
                None,
                context.invocation.workflow_context.get("execution_id"),
                context.invocation.workflow_context.get("created_by_user_id"),
            ),
            context,
        )
        return AAPJobTemplateOutput.model_validate(result["output"])
