from enum import Enum


class WorkflowLaunchRejectedProblemReason(str, Enum):
    EXECUTION_RUN_DENIED = "execution_run_denied"
    PRINCIPAL_INACTIVE = "principal_inactive"
    STEP_TYPE_DENIED = "step_type_denied"

    def __str__(self) -> str:
        return str(self.value)
