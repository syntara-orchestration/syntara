"""Temporal activity input models for form prompts."""

from typing import Any, TypedDict


class FormPromptActivityInput(TypedDict):
    """Named, typed input for creating a form prompt from a workflow."""

    execution_id: str
    prompt_node_id: str
    name: str
    form_definition: dict[str, Any]
    timeout_at: str | None
    responder_user_ids: list[str] | None
    responder_group_ids: list[str] | None
    project_id: str
    loop_iteration_path: list[int]
    temporal_activity_id: str | None
    message: str | None
    submit_label: str | None
    success_message: str | None
    css_override: str | None
