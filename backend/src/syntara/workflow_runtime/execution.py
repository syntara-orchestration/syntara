"""Public workflow execution facade.

Application services use this module instead of depending on a concrete
execution engine. The current implementation is Temporal-backed.
"""

from syntara.workflow_runtime.engines.temporal.services.temporal_execution_service import (
    TemporalExecutionService as WorkflowExecutionService,
)
from syntara.workflow_runtime.engines.temporal.services.temporal_execution_service import (
    create_temporal_execution_service as create_workflow_execution_service,
)

__all__ = ["WorkflowExecutionService", "create_workflow_execution_service"]
