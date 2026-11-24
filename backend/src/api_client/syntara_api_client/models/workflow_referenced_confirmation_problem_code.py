from enum import Enum


class WorkflowReferencedConfirmationProblemCode(str, Enum):
    WORKFLOW_REFERENCED_CONFIRMATION_REQUIRED = "WORKFLOW_REFERENCED_CONFIRMATION_REQUIRED"

    def __str__(self) -> str:
        return str(self.value)
