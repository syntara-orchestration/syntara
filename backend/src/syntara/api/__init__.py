"""Syntara API - A distributed multi-agent system.

Syntara enables coordinated AI agents to work together on complex tasks.
"""

# ===========================================================
# Import exception classes to trigger exception registration
# -----------------------------------------------------------
from syntara.agent_orchestrator.exceptions import LLMConfigurationError
from syntara.approvals.exceptions import (
    ApprovalAlreadyDecidedError,
    ApprovalAlreadyRequestedError,
    ApprovalNotFoundError,
)
from syntara.core.exceptions import SafeValueError
from syntara.files.exceptions import FileContentNotFoundError, FileError, FileIntegrityError, FileValidationError
from syntara.tool_manager.exceptions import (
    ProviderNameConflictError,
    ProviderNotFoundError,
    ToolBulkUpdateValidationError,
    ToolManagerError,
    ToolNotFoundError,
    ToolRefreshError,
)
from syntara.workflows.exceptions import (
    ExecutionNotFoundError,
    TemporalUnavailableError,
    WorkflowNameConflictError,
    WorkflowNotFoundError,
    WorkflowNotPublishedError,
    WorkflowValidationError,
    WorkflowVersionNotFoundError,
)
