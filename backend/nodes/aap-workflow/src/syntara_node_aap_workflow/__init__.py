"""SDK aap-workflow node."""

from syntara_node_runtime.models import AAPWorkflowJobTemplateExecutorParameters, AAPWorkflowJobTemplateOutput
from syntara_node_runtime.runtime import RuntimeContext, run_async
from syntara_sdk import ExecutionContext, TaskNode

from .executor import execute_aap_workflow_job_template_activity


class Node(TaskNode[AAPWorkflowJobTemplateExecutorParameters, AAPWorkflowJobTemplateOutput]):
    """Preserve the existing workflow contract through the SDK."""

    def __init__(self) -> None:
        """Initialize the node contract and execution state."""
        super().__init__(AAPWorkflowJobTemplateExecutorParameters, AAPWorkflowJobTemplateOutput)

    def run(
        self, _inputs: AAPWorkflowJobTemplateExecutorParameters, context: ExecutionContext
    ) -> AAPWorkflowJobTemplateOutput:
        """Execute validated inputs using the portable runtime."""
        if not isinstance(context, RuntimeContext):
            message = "Use the container runner with a RuntimeContext"
            raise TypeError(message)
        result = run_async(
            lambda: execute_aap_workflow_job_template_activity(
                context.input_config(),
                None,
                context.invocation.workflow_context.get("execution_id"),
                context.invocation.workflow_context.get("created_by_user_id"),
            ),
            context,
        )
        return AAPWorkflowJobTemplateOutput.model_validate(result["output"])
