from enum import Enum


class WorkflowPublishTriggerRemovalConfirmationProblemCode(str, Enum):
    WORKFLOW_PUBLISH_TRIGGER_REMOVAL_CONFIRMATION_REQUIRED = "WORKFLOW_PUBLISH_TRIGGER_REMOVAL_CONFIRMATION_REQUIRED"

    def __str__(self) -> str:
        return str(self.value)
