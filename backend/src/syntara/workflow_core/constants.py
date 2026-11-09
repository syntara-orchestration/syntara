"""Constants shared by workflow definitions, API services, and runtimes."""

from syntara.workflow_core.aap_types import AAPJobTerminalStatus

AGENT_EXECUTION_TIMEOUT_SECONDS = 3600
AAP_JOB_TERMINAL_STATUSES = {status.lower() for status in AAPJobTerminalStatus}

__all__ = ["AAP_JOB_TERMINAL_STATUSES", "AGENT_EXECUTION_TIMEOUT_SECONDS"]
