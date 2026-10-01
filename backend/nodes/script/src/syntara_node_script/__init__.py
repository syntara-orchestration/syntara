"""SDK node for isolated Python and Bash execution."""

from typing import Any

from syntara_node_runtime.models import ScriptExecutorParameters, ScriptOutput
from syntara_node_runtime.runtime import NodeFailure, RuntimeContext, run_async
from syntara_sdk import ExecutionContext, TaskNode

from .executor import ScriptExecutionError, execute_script


class Node(TaskNode[ScriptExecutorParameters, ScriptOutput]):
    """Run raw workflow code and preserve bounded process output."""

    def __init__(self) -> None:
        """Initialize the node contract and execution state."""
        super().__init__(ScriptExecutorParameters, ScriptOutput)

    def run(self, inputs: ScriptExecutorParameters, context: ExecutionContext) -> ScriptOutput:
        """Execute validated inputs using the portable runtime."""
        if not isinstance(context, RuntimeContext):
            message = "Use the container runner with a RuntimeContext"
            raise TypeError(message)

        async def invoke() -> dict[str, Any]:
            """Provide the invoke operation."""
            config = context.input_config()
            config.update(inputs.model_dump(mode="json"))
            try:
                return await execute_script(config, None)
            except ScriptExecutionError as exc:
                output = ScriptOutput(return_code=exc.exit_code, stdout=exc.stdout, stderr=exc.stderr)
                raise NodeFailure(str(exc), {"output": output.model_dump()}, type="ScriptExecutionError") from None
            except TimeoutError:
                message = "Script execution timed out"
                raise NodeFailure(message, {"output": ScriptOutput().model_dump()}, type="TimeoutError") from None

        result = run_async(invoke, context)
        return ScriptOutput.model_validate(result["output"])
