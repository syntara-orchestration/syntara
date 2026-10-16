from enum import Enum


class NodeType(str, Enum):
    AAP_JOB_TEMPLATE = "aap_job_template"
    AAP_WORKFLOW_JOB_TEMPLATE = "aap_workflow_job_template"
    AGENTIC = "agentic"
    APPROVAL = "approval"
    CONDITION = "condition"
    CONVERGE = "converge"
    EDA_TRIGGER = "eda_trigger"
    FORM_PROMPT = "form_prompt"
    HTTP_REQUEST = "http_request"
    INTERNAL_ACTIVITY = "internal_activity"
    LOOP = "loop"
    MANUAL_TRIGGER = "manual_trigger"
    SCHEDULED_TRIGGER = "scheduled_trigger"
    SCRIPT = "script"
    SWITCH = "switch"
    WAIT = "wait"
    WEBHOOK_TRIGGER = "webhook_trigger"

    def __str__(self) -> str:
        return str(self.value)
